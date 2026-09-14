"""Validate a generated wheel's RECORD and exercise its installed payload."""
import base64
import csv
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import zipfile


def verify_wheel(path):
    with zipfile.ZipFile(path) as wheel:
        files = {}
        for info in wheel.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.startswith('/') or '..' in PurePosixPath(name).parts or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f'unsafe wheel member: {name}')
            if name in files:
                raise ValueError(f'duplicate wheel member: {name}')
            files[name] = wheel.read(info)
        records = [n for n in files if n.count('/') == 1 and n.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise ValueError('expected one wheel RECORD')
        record = records[0]
        rows = list(csv.reader(io.StringIO(files[record].decode())))
        if any(len(r) != 3 for r in rows) or len({r[0] for r in rows}) != len(rows):
            raise ValueError('invalid or duplicate RECORD row')
        if {r[0] for r in rows} != set(files):
            raise ValueError('RECORD does not cover exactly the wheel files')
        for name, encoded_hash, size in rows:
            if name == record:
                if encoded_hash or size:
                    raise ValueError('RECORD must leave its own hash and size empty')
                continue
            algorithm, separator, expected = encoded_hash.partition('=')
            if not separator or algorithm not in ('sha256', 'sha384', 'sha512'):
                raise ValueError(f'unsupported wheel digest: {encoded_hash}')
            actual = base64.urlsafe_b64encode(hashlib.new(algorithm, files[name]).digest()).decode().rstrip('=')
            if actual != expected or str(len(files[name])) != size:
                raise ValueError(f'wheel RECORD mismatch: {name}')


def install_and_import(wheel, destination, module):
    verify_wheel(wheel)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(destination)
    env = dict(os.environ, PYTHONPATH=str(destination), PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable, '-S', '-c',
        'import importlib, pathlib, sys; m=importlib.import_module(sys.argv[1]); '
        'assert pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[2])); '
        'assert m.ANSWER == 42', module, str(destination)], cwd=destination, env=env, check=True)
