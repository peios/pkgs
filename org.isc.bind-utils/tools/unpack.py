from pathlib import Path
import sys, tarfile
source, dest, version = sys.argv[1:]
archives = list(Path(source).iterdir())
assert len(archives) == 1 and archives[0].is_file()
with tarfile.open(archives[0]) as tf:
    for member in tf:
        assert member.name.rstrip('/') == 'bind-' + version or member.name.startswith('bind-' + version + '/'), member.name
    tf.extractall(dest, filter='data')
