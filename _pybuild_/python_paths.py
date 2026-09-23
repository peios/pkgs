"""Shared interpreter-derived library layout for installation and qualification."""
from pathlib import Path, PurePosixPath
import sys
import sysconfig


def library_path():
    # Every Python recipe builds in the native Peios root, whose interpreter
    # must report exactly the distribution's site-packages.
    path = sysconfig.get_path('platlib')
    if not path or not path.startswith('/') or '..' in PurePosixPath(path).parts:
        raise ValueError(f'unsafe interpreter library path: {path!r}')
    expected = f'/usr/lib/x86_64-linux-peios/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    if path != expected:
        raise ValueError(f'interpreter uses {path}, expected {expected}')
    return path


def staged_site(stage):
    return Path(stage).absolute() / library_path().lstrip('/')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python_paths.py STAGE')
    print(staged_site(sys.argv[1]))
