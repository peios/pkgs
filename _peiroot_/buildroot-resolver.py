#!/usr/bin/env python3
"""Answer host lookups in a networked native build root.

Peios glibc resolves hosts only through resolvd (libnss_peios_net.so.2 over
/run/resolvd/resolv.sock). A build root runs no resolvd: the real service
reads its policy from the registry, authorises callers by Peios token and
binds the 127.0.0.53 stub, none of which a sandbox on a build host provides.

This stand-in serves the two queries the NSS shim sends -- `lookup` and
`reverse` -- in resolvd's native protocol, and forwards them as plain DNS to
the nameservers in the resolv.conf Pekit copies into networked roots. It has
no cache and no policy, and it speaks DNS itself: resolving through the
standard library would route back through the shim to this process.

It exists only for the lifetime of one sandboxed vendor job (see
entry.sh) and is never part of a package.
"""
import ipaddress
import os
import random
import socket
import socketserver
import struct
import sys
import threading

SOCKET_PATH = '/run/resolvd/resolv.sock'
MAX_MESSAGE = 65536
DNS_PORT = 53
TIMEOUT = 2.0
ATTEMPTS = 3
A, CNAME, PTR, AAAA = 1, 5, 12, 28
NOERROR, NXDOMAIN = 0, 3


class Unavailable(Exception):
    """No configured server gave a usable answer."""


# ---- MessagePack: the subset resolvd's protocol uses -----------------------

def pack(value, out):
    if value is None:
        out.append(0xc0)
    elif value is True or value is False:
        out.append(0xc3 if value else 0xc2)
    elif isinstance(value, int):
        if value < 0:
            raise ValueError('negative integers are not part of the protocol')
        if value < 0x80:
            out.append(value)
        elif value <= 0xff:
            out += bytes([0xcc, value])
        elif value <= 0xffff:
            out += b'\xcd' + struct.pack('>H', value)
        elif value <= 0xffffffff:
            out += b'\xce' + struct.pack('>I', value)
        else:
            out += b'\xcf' + struct.pack('>Q', value)
    elif isinstance(value, str):
        data = value.encode()
        n = len(data)
        if n < 32:
            out.append(0xa0 | n)
        elif n <= 0xff:
            out += bytes([0xd9, n])
        elif n <= 0xffff:
            out += b'\xda' + struct.pack('>H', n)
        else:
            out += b'\xdb' + struct.pack('>I', n)
        out += data
    elif isinstance(value, (bytes, bytearray)):
        n = len(value)
        if n <= 0xff:
            out += bytes([0xc4, n])
        elif n <= 0xffff:
            out += b'\xc5' + struct.pack('>H', n)
        else:
            out += b'\xc6' + struct.pack('>I', n)
        out += value
    elif isinstance(value, list):
        n = len(value)
        if n < 16:
            out.append(0x90 | n)
        else:
            out += b'\xdc' + struct.pack('>H', n)
        for item in value:
            pack(item, out)
    elif isinstance(value, dict):
        n = len(value)
        if n < 16:
            out.append(0x80 | n)
        else:
            out += b'\xde' + struct.pack('>H', n)
        for key, item in value.items():
            pack(key, out)
            pack(item, out)
    else:
        raise TypeError(type(value))
    return out


def unpack(data, pos=0):
    """Return (value, next position). Raises ValueError on malformed input."""
    def take(n):
        nonlocal pos
        if pos + n > len(data):
            raise ValueError('truncated message')
        chunk = data[pos:pos + n]
        pos += n
        return chunk

    b = take(1)[0]
    if b < 0x80:
        return b, pos
    if b >= 0xe0:
        return b - 0x100, pos
    if 0x80 <= b <= 0x8f or b in (0xde, 0xdf):
        n = b & 0x0f if b <= 0x8f else struct.unpack('>H' if b == 0xde else '>I', take(2 if b == 0xde else 4))[0]
        result = {}
        for _ in range(n):
            key, pos = unpack(data, pos)
            if not isinstance(key, str) or key in result:
                raise ValueError('map keys must be distinct strings')
            result[key], pos = unpack(data, pos)
        return result, pos
    if 0x90 <= b <= 0x9f or b in (0xdc, 0xdd):
        n = b & 0x0f if b <= 0x9f else struct.unpack('>H' if b == 0xdc else '>I', take(2 if b == 0xdc else 4))[0]
        items = []
        for _ in range(n):
            item, pos = unpack(data, pos)
            items.append(item)
        return items, pos
    if 0xa0 <= b <= 0xbf or b in (0xd9, 0xda, 0xdb):
        n = b & 0x1f if b <= 0xbf else int.from_bytes(take({0xd9: 1, 0xda: 2, 0xdb: 4}[b]), 'big')
        return take(n).decode(), pos
    if b in (0xc4, 0xc5, 0xc6):
        n = int.from_bytes(take({0xc4: 1, 0xc5: 2, 0xc6: 4}[b]), 'big')
        return bytes(take(n)), pos
    if b == 0xc0:
        return None, pos
    if b in (0xc2, 0xc3):
        return b == 0xc3, pos
    if b in (0xcc, 0xcd, 0xce, 0xcf):
        return int.from_bytes(take({0xcc: 1, 0xcd: 2, 0xce: 4, 0xcf: 8}[b]), 'big'), pos
    raise ValueError(f'unsupported MessagePack type 0x{b:02x}')


# ---- DNS client -------------------------------------------------------------

def read_config(path='/etc/resolv.conf'):
    servers, search, ndots = [], [], 1
    with open(path) as f:
        for line in f:
            words = line.split('#', 1)[0].split(';', 1)[0].split()
            if not words:
                continue
            if words[0] == 'nameserver' and len(words) > 1:
                try:
                    servers.append(str(ipaddress.ip_address(words[1].split('%', 1)[0])))
                except ValueError:
                    pass
            elif words[0] in ('search', 'domain'):
                search = [w.strip('.') for w in words[1:] if w.strip('.')]
            elif words[0] == 'options':
                for option in words[1:]:
                    if option.startswith('ndots:'):
                        # glibc ignores a malformed option; so does this.
                        try:
                            ndots = min(max(int(option[6:] or 1), 0), 15)
                        except ValueError:
                            pass
    if not servers:
        raise SystemExit('buildroot-resolver: resolv.conf names no nameserver')
    return servers, search, ndots


def encode_name(name):
    out = bytearray()
    for label in name.rstrip('.').split('.') if name.rstrip('.') else []:
        raw = label.encode('idna') if not label.isascii() else label.encode()
        if not 0 < len(raw) < 64:
            raise ValueError(f'invalid DNS label in {name!r}')
        out += bytes([len(raw)]) + raw
    return bytes(out + b'\0')


def decode_name(msg, pos):
    labels, jumps, end = [], 0, None
    while True:
        if pos >= len(msg):
            raise ValueError('truncated name')
        n = msg[pos]
        if n & 0xc0 == 0xc0:
            if pos + 1 >= len(msg) or jumps > 32:
                raise ValueError('bad compression pointer')
            if end is None:
                end = pos + 2
            pos = ((n & 0x3f) << 8) | msg[pos + 1]
            jumps += 1
            continue
        if n == 0:
            return '.'.join(labels), (end if end is not None else pos + 1)
        labels.append(msg[pos + 1:pos + 1 + n].decode('ascii', 'replace'))
        pos += 1 + n


def exchange(server, packet, tcp):
    family = socket.AF_INET6 if ':' in server else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as s:
        s.settimeout(TIMEOUT)
        s.connect((server, DNS_PORT))
        if not tcp:
            s.send(packet)
            return s.recv(65535)
        s.sendall(struct.pack('>H', len(packet)) + packet)
        data = b''
        while len(data) < 2:
            chunk = s.recv(2 - len(data))
            if not chunk:
                raise OSError('connection closed')
            data += chunk
        want, data = struct.unpack('>H', data)[0], b''
        while len(data) < want:
            chunk = s.recv(want - len(data))
            if not chunk:
                raise OSError('connection closed')
            data += chunk
        return data


def query(servers, name, rtype):
    """Return (rcode, [(owner, type, ttl, rdata, rdata offset, message)])."""
    for _ in range(ATTEMPTS):
        for server in servers:
            ident = random.getrandbits(16)
            packet = struct.pack('>HHHHHH', ident, 0x0100, 1, 0, 0, 0) + encode_name(name) + struct.pack('>HH', rtype, 1)
            try:
                msg = exchange(server, packet, tcp=False)
                if len(msg) >= 12 and msg[2] & 0x02:
                    msg = exchange(server, packet, tcp=True)
            except OSError:
                continue
            if len(msg) < 12:
                continue
            got, flags, qd, an = struct.unpack('>HHHH', msg[:8])
            if got != ident or not flags & 0x8000:
                continue
            rcode = flags & 0x000f
            if rcode not in (NOERROR, NXDOMAIN):
                continue
            pos = 12
            try:
                for _ in range(qd):
                    _, pos = decode_name(msg, pos)
                    pos += 4
                records = []
                for _ in range(an):
                    owner, pos = decode_name(msg, pos)
                    typ, _cls, ttl, length = struct.unpack('>HHIH', msg[pos:pos + 10])
                    pos += 10
                    records.append((owner, typ, ttl, msg[pos:pos + length], pos, msg))
                    pos += length
            except (ValueError, struct.error):
                continue
            return rcode, records
    raise Unavailable(name)


def candidates(name, search, ndots):
    # A trailing dot makes the name absolute: never expand it with search
    # domains, exactly as glibc does.
    absolute = name.endswith('.')
    name = name.rstrip('.')
    if absolute or not search:
        return [name]
    expanded = [f'{name}.{domain}' for domain in search]
    return [name] + expanded if name.count('.') >= ndots else expanded + [name]


def chase(records, name, rtype):
    """Follow CNAMEs from name; return (canonical, [(address text, ttl)])."""
    canonical = name.rstrip('.').lower()
    for _ in range(16):
        target = next((decode_name(msg, off)[0] for owner, typ, _, _, off, msg in records
                       if typ == CNAME and owner.lower() == canonical), None)
        if target is None:
            break
        canonical = target.lower()
    found = [(str(ipaddress.ip_address(data)), ttl) for owner, typ, ttl, data, _, _ in records
             if typ == rtype and owner.lower() == canonical and len(data) in (4, 16)]
    return canonical, found


def lookup(config, name, family):
    servers, search, ndots = config
    types = {'inet': [A], 'inet6': [AAAA]}.get(family, [A, AAAA])
    nodata = None
    for candidate in candidates(name, search, ndots):
        addresses, canonical, exists = [], candidate, False
        for rtype in types:
            rcode, records = query(servers, candidate, rtype)
            if rcode == NOERROR:
                exists = True
                canonical, found = chase(records, candidate, rtype)
                addresses += found
        if addresses:
            return 'found', canonical, addresses
        if exists and nodata is None:
            nodata = canonical
    # NODATA (the name exists without addresses) is found with none.
    return ('notfound', name, []) if nodata is None else ('found', nodata, [])


def reverse(config, address):
    servers = config[0]
    ptr = ipaddress.ip_address(address).reverse_pointer
    rcode, records = query(servers, ptr, PTR)
    if rcode == NXDOMAIN:
        return 'notfound', []
    out = []
    for owner, typ, ttl, data, off, msg in records:
        if typ == PTR:
            target = decode_name(msg, off)[0]
            out.append({'name': owner, 'type': PTR, 'ttl': ttl,
                        'data': encode_name(target), 'text': target + '.'})
    return 'found', out


# ---- resolvd's native socket ------------------------------------------------

def reply(request, config):
    query_name = request.get('query')
    try:
        if query_name == 'lookup':
            name = request.get('name')
            if not isinstance(name, str) or not name:
                return {'ok': False, 'error': 'lookup requires a name'}
            family = request.get('family') or 'any'
            if name.rstrip('.').lower() == 'localhost' or name.rstrip('.').lower().endswith('.localhost'):
                outcome, canonical = 'found', 'localhost'
                addresses = [(a, 0) for a, fam in (('127.0.0.1', 'inet'), ('::1', 'inet6')) if family in ('any', fam)]
                source = 'synthetic'
            else:
                outcome, canonical, addresses = lookup(config, name, family)
                source = 'dns'
            return {'ok': True, 'kind': 'addresses', 'outcome': outcome, 'canonical': canonical,
                    'addresses': [{'address': a, 'ttl': ttl} for a, ttl in addresses],
                    'source': source, 'validation': 'unvalidated'}
        if query_name == 'reverse':
            outcome, records = reverse(config, request.get('address'))
            return {'ok': True, 'kind': 'answer', 'outcome': outcome, 'records': records,
                    'source': 'dns', 'server': None, 'interface': None,
                    'validation': 'unvalidated', 'rcode': NXDOMAIN if outcome == 'notfound' else NOERROR}
        return {'ok': False, 'error': f'the build-root resolver does not answer {query_name!r}'}
    except Unavailable:
        if query_name == 'reverse':
            return {'ok': True, 'kind': 'answer', 'outcome': 'unavailable', 'records': [],
                    'source': 'dns', 'server': None, 'interface': None,
                    'validation': 'unvalidated', 'rcode': 0}
        return {'ok': True, 'kind': 'addresses', 'outcome': 'unavailable', 'canonical': request.get('name', ''),
                'addresses': [], 'source': 'dns', 'validation': 'unvalidated'}
    except ValueError as e:
        return {'ok': False, 'error': str(e)}


def recv_exact(conn, n):
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError('client closed')
        data += chunk
    return data


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        conn = self.request
        conn.settimeout(30)
        try:
            length = struct.unpack('<I', recv_exact(conn, 4))[0]
            if length > MAX_MESSAGE:
                return
            request, end = unpack(recv_exact(conn, length))
            if end != length or not isinstance(request, dict):
                raise ValueError('malformed request')
            answer = reply(request, self.server.config)
        except (ValueError, UnicodeDecodeError) as e:
            answer = {'ok': False, 'error': str(e)}
        except (ConnectionError, OSError):
            return
        payload = bytes(pack(answer, bytearray()))
        conn.sendall(struct.pack('<I', len(payload)) + payload)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]
    config = read_config(paths[0] if paths else '/etc/resolv.conf')
    path = os.environ.get('BUILDROOT_RESOLVER_SOCKET', SOCKET_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    server = Server(path, Handler)
    server.config = config
    # Readiness: the socket is bound and listening before the parent returns,
    # so the caller needs no polling. The child is reaped with the sandbox.
    if '--foreground' not in sys.argv and os.fork():
        os._exit(0)
    server.serve_forever()


if __name__ == '__main__':
    main()
