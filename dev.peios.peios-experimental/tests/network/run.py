#!/usr/bin/env python3
"""Boot the installed networking clients under native Peios identity checks."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--kernel', type=Path, required=True, help='Peios bzImage with built-in boot drivers')
p.add_argument('--root', type=Path, required=True, help='composed Experimental system root')
p.add_argument('--libpeios-static', type=Path, required=True, help='libpeios.a for the static fixture')
p.add_argument('--work', type=Path, required=True, help='new disposable output directory')
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
queue = []
for name in ['ping', 'curl']:
    target = guest / name
    shutil.copy2(a.root / 'usr/bin' / name, target)
    queue.append(target)
seen = set()
while queue:
    binary = queue.pop()
    dynamic = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    for name in re.findall(r'Shared library: \[([^]]+)\]', dynamic):
        if name in seen:
            continue
        seen.add(name)
        source = a.root / 'usr/lib/x86_64-linux-peios' / name
        # Absolute payload symlinks refer to the composed root, never the host.
        while source.is_symlink():
            link = source.readlink()
            source = a.root / str(link).lstrip('/') if link.is_absolute() else source.parent / link
        target = libs / name
        shutil.copy2(source, target)
        queue.append(target)
(guest / 'lib64').mkdir()
shutil.copy2(a.root / 'usr/lib/x86_64-linux-peios/ld-linux-x86-64.so.2',
             guest / 'lib64/ld-linux-x86-64.so.2')
archive = a.work / 'network.cpio'
entries = sorted(str(f.relative_to(guest)) for f in guest.rglob('*'))
with archive.open('wb') as output:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc'], cwd=guest,
                   input=('\0'.join(['.'] + entries) + '\0').encode(),
                   stdout=output, check=True)
log = a.work / 'network-vm.log'
with log.open('w') as output:
    subprocess.run([
        'qemu-system-x86_64', '-m', '1024', '-smp', '2', '-nographic', '-no-reboot',
        '-serial', 'mon:stdio', '-machine', 'accel=kvm:tcg', '-cpu', 'max',
        '-kernel', str(a.kernel.resolve()), '-initrd', str(archive.resolve()),
        '-append', 'console=ttyS0 quiet loglevel=4 panic=-1 kunit.enable=0 rdinit=/init',
    ], stdout=output, stderr=subprocess.STDOUT, timeout=90, check=True)
result = log.read_text()
if 'NETWORK_FAIL:' in result or 'NETWORK_PASS:' not in result:
    raise SystemExit(f'Native networking checks failed: {log}')
print(next(line for line in result.splitlines() if line.startswith('NETWORK_PASS:')))
print(f'Log: {log}')
