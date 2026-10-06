#!/usr/bin/env python3
"""Run mock DNS/stream/socket tests against a composed root's actual binaries."""
from pathlib import Path
import argparse
import shlex
import subprocess
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('root', type=Path)
a = p.parse_args()
root = a.root.resolve()
catalogue = Path(__file__).resolve().parents[3]
# Keep the mock servers on the host. The command sees only its composed
# runtime root, with the same network namespace as those local servers.
with tempfile.TemporaryDirectory(prefix='network-installed-') as tmp:
    for package, command in [
        ('org.isc.bind-utils', 'dig'),
        ('org.debian.netcat-openbsd', 'nc'),
        ('org.kernel.iproute2', 'ss'),
    ]:
        wrapper = Path(tmp) / command
        wrapper.write_text('#!/bin/sh\nexec bwrap --die-with-parent --ro-bind '
                           + shlex.quote(str(root))
                           + ' / --dev /dev --proc /proc --tmpfs /tmp -- '
                           + '/usr/bin/' + command + ' "$@"\n')
        wrapper.chmod(0o755)
        subprocess.run([sys.executable,
                        str(catalogue / package / 'tests/installed.py'),
                        str(wrapper)], check=True)
print('NETWORK_COMPOSED_RUNTIME_PASS')
