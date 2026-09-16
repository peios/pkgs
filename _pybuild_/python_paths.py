"""Shared interpreter-derived library layout for installation and qualification."""
import os
from pathlib import Path, PurePosixPath
import sys
import sysconfig


def library_path(provider=None):
    provider = os.environ.get('PEKIT_DEPENDENCY_PROVIDER', '') if provider is None else provider
    path = sysconfig.get_path('platlib')
    if not path or not path.startswith('/') or '..' in PurePosixPath(path).parts:
        raise ValueError(f'unsafe interpreter library path: {path!r}')
    expected = f'/usr/lib/x86_64-linux-peios/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    if provider == 'peipkg':
        if path != expected:
            raise ValueError(f'native interpreter uses {path}, expected {expected}')
    elif provider not in ('apt', ''):
        raise ValueError(f'unsupported Python dependency provider: {provider}')
    # Reference interpreters stage the same distribution layout, using their
    # own ABI version. Their /usr/local sysconfig default is not package policy.
    return expected if provider in ('apt', 'peipkg') else path


def staged_site(stage, provider=None):
    return Path(stage).absolute() / library_path(provider).lstrip('/')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python_paths.py STAGE')
    print(staged_site(sys.argv[1]))
