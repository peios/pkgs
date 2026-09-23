import importlib.util
from pathlib import Path
import socket
import socketserver
import struct
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location(
    "resolver", Path(__file__).with_name("buildroot-resolver.py"))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

# A zone for the fake upstream: www.example.test is a CNAME to a host with one
# A record and no AAAA; big.example.test only answers over TCP.
A_ADDR = bytes([192, 0, 2, 7])


def name(n):
    return r.encode_name(n)


def answer(query, rcode, records, truncated=False):
    ident = struct.unpack('>H', query[:2])[0]
    qend = 12
    while query[qend]:
        qend += 1 + query[qend]
    question = query[12:qend + 5]
    flags = 0x8180 | rcode | (0x0200 if truncated else 0)
    out = struct.pack('>HHHHHH', ident, flags, 1, len(records), 0, 0) + question
    for owner, rtype, rdata in records:
        # Compress owners equal to the question name, as real servers do.
        owner_bytes = b'\xc0\x0c' if name(owner) == query[12:qend + 1] else name(owner)
        out += owner_bytes + struct.pack('>HHIH', rtype, 1, 300, len(rdata)) + rdata
    return out


def respond(query, tcp):
    qend = 12
    while query[qend]:
        qend += 1 + query[qend]
    qname, _ = r.decode_name(query, 12)
    qtype = struct.unpack('>H', query[qend + 1:qend + 3])[0]
    if qname == 'www.example.test':
        records = [('www.example.test', r.CNAME, name('host.example.test'))]
        if qtype == r.A:
            records.append(('host.example.test', r.A, A_ADDR))
        return answer(query, r.NOERROR, records)
    if qname == 'big.example.test':
        if not tcp:
            return answer(query, r.NOERROR, [], truncated=True)
        return answer(query, r.NOERROR, [('big.example.test', r.A, A_ADDR)] if qtype == r.A else [])
    if qname == '7.2.0.192.in-addr.arpa' and qtype == r.PTR:
        return answer(query, r.NOERROR, [(qname, r.PTR, name('host.example.test'))])
    return answer(query, r.NXDOMAIN, [])


class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        sock.sendto(respond(data, tcp=False), self.client_address)


class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        n = struct.unpack('>H', self.request.recv(2))[0]
        reply = respond(self.request.recv(n), tcp=True)
        self.request.sendall(struct.pack('>H', len(reply)) + reply)


class ResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        socketserver.TCPServer.allow_reuse_address = True
        cls.tcp = socketserver.ThreadingTCPServer(('127.0.0.1', 0), TCP)
        port = cls.tcp.server_address[1]
        cls.udp = socketserver.ThreadingUDPServer(('127.0.0.1', port), UDP)
        for server in (cls.tcp, cls.udp):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.old_port, r.DNS_PORT = r.DNS_PORT, port
        cls.config = (['127.0.0.1'], [], 1)

    @classmethod
    def tearDownClass(cls):
        r.DNS_PORT = cls.old_port
        for server in (cls.tcp, cls.udp):
            server.shutdown()
            server.server_close()

    def test_lookup_chases_cname(self):
        self.assertEqual(r.lookup(self.config, 'www.example.test', 'any'),
                         ('found', 'host.example.test', [('192.0.2.7', 300)]))

    def test_nodata_is_found_without_addresses(self):
        self.assertEqual(r.lookup(self.config, 'www.example.test', 'inet6'),
                         ('found', 'host.example.test', []))

    def test_nxdomain_is_notfound(self):
        self.assertEqual(r.lookup(self.config, 'missing.test', 'any'),
                         ('notfound', 'missing.test', []))

    def test_truncated_answer_retries_over_tcp(self):
        self.assertEqual(r.lookup(self.config, 'big.example.test', 'inet'),
                         ('found', 'big.example.test', [('192.0.2.7', 300)]))

    def test_search_domains_follow_ndots(self):
        self.assertEqual(r.candidates('www', ['example.test'], 1),
                         ['www.example.test', 'www'])
        self.assertEqual(r.candidates('a.b', ['example.test'], 1),
                         ['a.b', 'a.b.example.test'])

    def test_reverse(self):
        outcome, records = r.reverse(self.config, '192.0.2.7')
        self.assertEqual(outcome, 'found')
        self.assertEqual(records[0]['text'], 'host.example.test.')
        self.assertEqual(records[0]['data'], name('host.example.test'))

    def test_unreachable_upstream_is_unavailable(self):
        with tempfile.TemporaryDirectory():
            old, r.TIMEOUT, r.ATTEMPTS = (r.TIMEOUT, r.ATTEMPTS), 0.05, 1
            try:
                reply = r.reply({'query': 'lookup', 'name': 'x.test'}, (['127.0.0.2'], [], 1))
            finally:
                r.TIMEOUT, r.ATTEMPTS = old
        self.assertEqual(reply['outcome'], 'unavailable')

    def test_native_wire_round_trip(self):
        # Bytes as libresolv's Request::Lookup encoder writes them: a fixmap of
        # three fixstr keys in order.
        request = (b'\x83\xa5query\xa6lookup\xa4name\xb0www.example.test'
                   b'\xa6family\xa3any')
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'resolv.sock')
            server = r.Server(path, r.Handler)
            server.config = self.config
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(path)
                    client.sendall(struct.pack('<I', len(request)) + request)
                    n = struct.unpack('<I', client.recv(4))[0]
                    data = b''
                    while len(data) < n:
                        data += client.recv(n - len(data))
            finally:
                server.shutdown()
                server.server_close()
        reply, end = r.unpack(data)
        self.assertEqual(end, n)
        # Key order is the libresolv Reply::Addresses encoding.
        self.assertEqual(list(reply), ['ok', 'kind', 'outcome', 'canonical',
                                       'addresses', 'source', 'validation'])
        self.assertEqual(reply['addresses'], [{'address': '192.0.2.7', 'ttl': 300}])

    def test_msgpack_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):
            r.unpack(b'\x82\xa1a\x01\xa1a\x02')

    def test_localhost_is_synthetic(self):
        reply = r.reply({'query': 'lookup', 'name': 'localhost', 'family': 'inet'}, self.config)
        self.assertEqual(reply['addresses'], [{'address': '127.0.0.1', 'ttl': 0}])
        self.assertEqual(reply['source'], 'synthetic')


if __name__ == '__main__':
    unittest.main()
