#!/usr/bin/env python3
"""Acquire an authenticated maintained musl source for the Debian reference SDK."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request

ORIGIN = 'https://musl.libc.org'
FINGERPRINT = '836489290BB6B70F99FFDA0556BCDB593020450F'

def download(url, output):
    with urllib.request.urlopen(url, timeout=120) as response:
        if not response.geturl().startswith(ORIGIN + '/'):
            raise ValueError('musl download redirected outside the declared origin')
        data = response.read()
    output.write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def acquire(recipe, output):
    output.mkdir(parents=True, exist_ok=False)
    download(ORIGIN + '/releases.html', output / 'releases.html')
    versions = {tuple(map(int, x.split('.'))) for x in re.findall(
        r'musl-(1\.2\.[0-9]+)\.tar\.gz', (output / 'releases.html').read_text())}
    version = max(v for v in versions if v >= (1, 2, 6))
    version = '.'.join(map(str, version))
    archive = output / f'musl-{version}.tar.gz'
    url = ORIGIN + '/releases/' + archive.name
    digest = download(url, archive)
    signature = archive.with_suffix(archive.suffix + '.asc')
    signature_digest = download(url + '.asc', signature)
    keyring = output / 'musl-release.gpg'
    subprocess.run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(keyring),
                    str(recipe / 'keys/musl-release.asc')], check=True)
    home = output / 'gnupg-home'; home.mkdir(mode=0o700)
    status = subprocess.check_output(['gpgv', '--homedir', str(home), '--status-fd', '1',
        '--keyring', str(keyring.resolve()), str(signature), str(archive)], text=True)
    valid = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    if len(valid) != 1 or FINGERPRINT not in (valid[0][2], valid[0][-1]):
        raise ValueError('musl source signature does not match the pinned release key')
    source = output / 'source'
    with tarfile.open(archive, 'r:gz') as bundle:
        bundle.extractall(source, filter='data')
    if sorted(x.name for x in source.iterdir()) != [f'musl-{version}']:
        raise ValueError('unexpected musl archive layout')
    (output / 'source-root.txt').write_text(f'musl-{version}\n')
    (output / 'inputs.json').write_text(json.dumps({'version': version, 'url': url,
        'sha256': digest, 'signature_sha256': signature_digest, 'signer': FINGERPRINT,
        'signature_status': status}, indent=2)+'\n')

if __name__ == '__main__':
    acquire(Path(sys.argv[1]), Path(sys.argv[2]))
