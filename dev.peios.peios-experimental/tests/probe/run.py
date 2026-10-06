#!/usr/bin/env python3
"""Boot the installed capture and network probing tools under native Peios identity checks."""
import argparse
from pathlib import Path
import re
import json
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--kernel', type=Path, required=True, help='Peios bzImage with built-in boot drivers')
p.add_argument('--root', type=Path, required=True, help='composed Experimental system root')
p.add_argument('--libpeios-static', type=Path, required=True, help='libpeios.a for the static fixture')
p.add_argument('--work', type=Path, required=True, help='new disposable output directory')
p.add_argument('--stages', type=Path, required=True, help='JSON map of package names to stages or composed root')
p.add_argument('--pcap-sdk', type=Path, help='libpcap SDK stage for headers; runtime library still comes from stages')
a = p.parse_args()
repo = Path(__file__).resolve().parents[4]
a.work.mkdir(parents=True, exist_ok=False)
guest = a.work / 'root'
guest.mkdir()
subprocess.run([
    'cc', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
    '-I' + str(repo / 'libpeios/include'), '-I' + str(repo / 'pkm/uapi'),
    str(Path(__file__).with_name('guest.c')), str(a.libpeios_static.resolve()),
    '-Wl,--allow-multiple-definition', '-ldl', '-lpthread', '-lm',
    '-o', str(guest / 'init'),
], check=True)
libs = guest / 'usr/lib/x86_64-linux-peios'
libs.mkdir(parents=True)
stages = {k: Path(v).resolve() for k,v in json.loads(a.stages.read_text()).items()}
stages['openssl-root']=a.root.resolve()
queue = []
(guest/'tools').mkdir()
tools = {'openssl':'openssl-root','socat':'org.dest-unreach.socat','tcpdump':'org.tcpdump.tcpdump',
         'mtr':'nl.bitwizard.mtr','mtr-packet':'nl.bitwizard.mtr',
         'traceroute':'net.sourceforge.traceroute','arping':'io.github.iputils.iputils',
         'ping':'io.github.iputils.iputils','nmap':'org.nmap.nmap'}
for name,pkg in tools.items():
    target = guest/'tools'/name
    shutil.copy2(stages[pkg]/'usr/bin'/name,target)
    queue.append(target)
shutil.copytree(stages['org.nmap.nmap']/'usr/share/nmap',guest/'usr/share/nmap')
pcap = stages['org.tcpdump.libpcap']
subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',
    '-I'+str((a.pcap_sdk or pcap)/'usr/include'),str(Path(__file__).with_name('pcap-check.c')),
    '-L'+str(pcap/'usr/lib/x86_64-linux-peios'),'-l:libpcap.so.1',
    '-Wl,-rpath-link,'+str(a.root.resolve()/'usr/lib/x86_64-linux-peios'),
    '-o',str(guest/'tools/pcap-check')],check=True)
queue.append(guest/'tools/pcap-check')
seen = set()
# pthread_cancel loads this library dynamically, outside ELF DT_NEEDED.
unwinder = libs / 'libgcc_s.so.1'
shutil.copy2(a.root / 'usr/lib/x86_64-linux-peios/libgcc_s.so.1', unwinder)
queue.append(unwinder)
while queue:
    binary = queue.pop()
    dynamic = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    for name in re.findall(r'Shared library: \[([^]]+)\]', dynamic):
        if name in seen:
            continue
        seen.add(name)
        libroot = pcap if name.startswith('libpcap.so') else a.root
        if not (libroot/'usr/lib/x86_64-linux-peios'/name).exists():
            libroot = next(root for root in stages.values() if (root/'usr/lib/x86_64-linux-peios'/name).exists())
        source = libroot / 'usr/lib/x86_64-linux-peios' / name
        # Absolute payload symlinks refer to the composed root, never the host.
        while source.is_symlink():
            link = source.readlink()
            source = libroot / str(link).lstrip('/') if link.is_absolute() else source.parent / link
        target = libs / name
        shutil.copy2(source, target)
        queue.append(target)
(guest / 'lib64').mkdir()
shutil.copy2(a.root / 'usr/lib/x86_64-linux-peios/ld-linux-x86-64.so.2',
             guest / 'lib64/ld-linux-x86-64.so.2')
archive = a.work / 'probe.cpio'
entries = sorted(str(f.relative_to(guest)) for f in guest.rglob('*'))
with archive.open('wb') as output:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc'], cwd=guest,
                   input=('\0'.join(['.'] + entries) + '\0').encode(),
                   stdout=output, check=True)
log = a.work / 'probe-vm.log'
with log.open('w') as output:
    subprocess.run([
        'qemu-system-x86_64', '-m', '1024', '-smp', '2', '-nographic', '-no-reboot',
        '-serial', 'mon:stdio', '-machine', 'accel=kvm:tcg', '-cpu', 'max',
        '-netdev','user,id=n0,restrict=on','-device','virtio-net-pci,netdev=n0',
        '-kernel', str(a.kernel.resolve()), '-initrd', str(archive.resolve()),
        '-append', 'console=ttyS0 quiet loglevel=4 panic=-1 kunit.enable=0 rdinit=/init',
    ], stdout=output, stderr=subprocess.STDOUT, timeout=180, check=True)
result = log.read_text(errors="replace")
if 'PROBE_FAIL:' in result or 'PROBE_PASS:' not in result:
    raise SystemExit(f'Native probing checks failed: {log}')
print(next(line for line in result.splitlines() if line.startswith('PROBE_PASS:')))
print(f'Log: {log}')
