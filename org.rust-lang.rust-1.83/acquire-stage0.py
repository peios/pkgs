#!/usr/bin/env python3
"""Acquire exact bootstrap inputs authenticated by the Rust source release.

Run only in Pekit's declared networked vendor target. The source release's PGP
verification authenticates src/stage0, including each requested SHA256. No
mutable channel document, host Rust installation or unsigned version fallback
participates in selection. Compilation remains offline.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

TARGET = 'x86_64-unknown-linux-gnu'
SERVER = 'https://static.rust-lang.org'


def selection(source):
    metadata = source / 'src/stage0'
    entries = {}
    for line in metadata.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        if key in entries:
            raise ValueError(f'duplicate stage0 metadata key: {key}')
        entries[key] = value
    if entries.get('dist_server') != SERVER:
        raise ValueError('unexpected bootstrap distribution server')
    version = entries['compiler_version']
    date = entries['compiler_date']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('bootstrap compiler is not a stable release')
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', date):
        raise ValueError('invalid bootstrap release date')
    selected = []
    for component in ('rustc', 'cargo', 'rust-std'):
        stem = f'{component}-{version}-{TARGET}'
        relative = f'dist/{date}/{stem}.tar.xz'
        checksum = entries[relative]
        if not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ValueError(f'invalid bootstrap checksum: {relative}')
        selected.append({'component': component, 'root': stem,
                         'url': f'{SERVER}/{relative}', 'sha256': checksum})
    return version, selected


def acquire(source, output):
    version, components = selection(source)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'stage0'
    if destination.exists():
        raise ValueError('refusing to reuse a pre-existing bootstrap installation')
    with tempfile.TemporaryDirectory(prefix='stage0-', dir=output) as temporary:
        temporary = Path(temporary)
        component_roots = []
        for entry in components:
            archive = temporary / (entry['root'] + '.tar.xz')
            with urllib.request.urlopen(entry['url'], timeout=120) as response, archive.open('xb') as stream:
                if not response.geturl().startswith(SERVER + '/'):
                    raise ValueError('bootstrap download redirected outside the declared origin')
                shutil.copyfileobj(response, stream)
            with archive.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual != entry['sha256']:
                    raise ValueError(f'bootstrap checksum mismatch: {entry["component"]}')
                stream.seek(0)
                with tarfile.open(fileobj=stream, mode='r:xz') as bundle:
                    # Reject absolute/traversing links and special files even though
                    # every byte has already been authenticated by signed source.
                    bundle.extractall(temporary / entry['component'], filter='data')
            # Preserve the authenticated distribution inputs for independent
            # offline verification from the signed source bundle.
            retained = output / 'stage0-archives'
            retained.mkdir(exist_ok=True)
            shutil.copyfile(archive, retained / archive.name)
            extracted = temporary / entry['component'] / entry['root']
            if sorted(p.name for p in extracted.parent.iterdir()) != [entry['root']]:
                raise ValueError('unexpected bootstrap archive layout')
            for component in (extracted / 'components').read_text().splitlines():
                if not re.fullmatch(r'[A-Za-z0-9_-]+', component):
                    raise ValueError('unsafe seed component name')
                component_roots.append(extracted / component)
            subprocess.run(['sh', str(extracted / 'install.sh'),
                            '--prefix=' + str(destination), '--disable-ldconfig'], check=True)
        # The installer may relocate files but must preserve every executable
        # and archive byte. Match installed binary inputs to authenticated raw
        # component files before discarding the extraction directories.
        identities = {}
        for installed in destination.rglob('*'):
            if not installed.is_file():
                continue
            with installed.open('rb') as stream:
                magic = stream.read(8)
            if not (magic.startswith(b'\x7fELF') or magic == b'!<arch>\n'):
                continue
            relative = installed.relative_to(destination)
            originals = [root / relative for root in component_roots if (root / relative).is_file()]
            if not originals:
                raise ValueError(f'installed seed binary has no authenticated original: {relative}')
            def digest(path):
                with path.open('rb') as stream:
                    return hashlib.file_digest(stream, 'sha256').hexdigest()
            expected = {digest(path) for path in originals}
            actual = digest(installed)
            if expected != {actual}:
                raise ValueError(f'installer changed authenticated seed binary: {relative}')
            identities[str(relative)] = actual
        if len(identities) < 10:
            raise ValueError('incomplete seed binary identity inventory')
        (output / 'stage0-byte-identities.json').write_text(json.dumps(identities, indent=2)+'\n')
    for executable in ('rustc', 'cargo'):
        actual = subprocess.check_output([str(destination / 'bin' / executable), '--version'], text=True).split()[1]
        if actual != version:
            raise ValueError(f'installed {executable} has unexpected version: {actual}')
    (output / 'stage0-inputs.json').write_text(json.dumps({
        'source_stage0_sha256': hashlib.sha256((source / 'src/stage0').read_bytes()).hexdigest(),
        'version': version, 'target': TARGET, 'components': components,
    }, indent=2) + '\n')


if __name__ == '__main__':
    acquire(Path(sys.argv[1]), Path(sys.argv[2]))
