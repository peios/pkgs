import errno, os, socket, subprocess, sys
from pathlib import Path
stage = Path(sys.argv[1]); bindir = stage / 'usr/bin'
for tool in ['ping', 'tracepath']:
    subprocess.run([str(bindir / tool), '-V'], check=True)
for args in [['-c1.1', '127.0.0.1'], ['-w0.1', '127.0.0.1'], ['-w0,1', '127.0.0.1']]:
    p = subprocess.run([str(bindir / 'ping'), *args], capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C'})
    assert p.returncode and 'invalid argument' in p.stderr, p
# The isolated Linux worker may deny ICMP datagram socket creation. The
# separately required Peios VM gate checks echo and native authorization.
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP):
        pass
except OSError as e:
    if e.errno not in (errno.EACCES, errno.EPERM):
        raise
    print('ICMP worker prerequisite unavailable; echo runtime gate requires the Peios VM')
else:
    subprocess.run(['meson', 'test', '--no-rebuild', '-C', str(stage / 'build'), '--print-errorlogs'], check=True)
subprocess.run([str(bindir / 'tracepath'), '-n', '-m', '2', '127.0.0.1'], check=True, timeout=15)
print('IPUTILS_INSTALLED_PASS')
