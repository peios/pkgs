"""Exercise the staged ZIP writer with an independent archive reader."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile
bin_dir, work = map(Path, sys.argv[1:])
work = work / 'zip-smoke'
work.mkdir(exist_ok=True)
os.chdir(work)
def run(*args):
    return subprocess.run([str(bin_dir / args[0]), *args[1:]], check=True, timeout=20, capture_output=True)
Path('input').mkdir(exist_ok=True)
Path('input/hello.txt').write_text('hello\n')
Path('input/two words.txt').write_text('spaces\n')
Path('input/café.txt').write_text('unicode\n')
run('zip', '-r', 'archive.zip', 'input')
with zipfile.ZipFile('archive.zip') as z:
    assert z.testzip() is None
    assert z.read('input/hello.txt') == b'hello\n'
    assert z.read('input/two words.txt') == b'spaces\n'
Path('input/hello.txt').write_text('changed\n')
run('zip', 'archive.zip', 'input/hello.txt')
with zipfile.ZipFile('archive.zip') as z:
    assert z.read('input/hello.txt') == b'changed\n'
run('zip', '-d', 'archive.zip', 'input/two words.txt')
with zipfile.ZipFile('archive.zip') as z:
    assert 'input/two words.txt' not in z.namelist()
run('zip', 'archive$(touch injected).zip', 'input/hello.txt')
run('zip', '-T', 'archive$(touch injected).zip')
assert not Path('injected').exists()
for command in ['zipcloak', 'zipnote', 'zipsplit']:
    run(command, '-h')
print('ZIP creation, replacement, deletion, spaces and command-injection regression passed')
