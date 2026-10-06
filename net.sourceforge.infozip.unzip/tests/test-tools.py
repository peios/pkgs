"""Read independently generated ZIP formats through the staged commands."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile
bin_dir, work = map(Path, sys.argv[1:])
work = work / 'unzip-smoke'
work.mkdir(exist_ok=True)
os.chdir(work)
def run(*args, **kwargs):
    return subprocess.run([str(bin_dir / args[0]), *args[1:]], timeout=20, capture_output=True, check=True, **kwargs)
for method in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2]:
    archive = f'method-{method}.zip'
    with zipfile.ZipFile(archive, 'w', compression=method) as z:
        z.writestr('two words.txt', b'archive payload\n')
    run('unzip', '-t', archive)
    assert run('unzip', '-p', archive).stdout == b'archive payload\n'
    run('unzip', '-q', '-o', archive, '-d', f'extract-{method}')
    assert Path(f'extract-{method}/two words.txt').read_bytes() == b'archive payload\n'
    assert b'two words.txt' in run('zipinfo', '-1', archive).stdout
with zipfile.ZipFile('zip64.zip', 'w') as z:
    with z.open('zip64.txt', 'w', force_zip64=True) as f:
        f.write(b'zip64\n')
assert run('unzip', '-p', 'zip64.zip').stdout == b'zip64\n'
# funzip is a streaming single-member reader; use unzip for ZIP64.
assert run('funzip', input=Path('method-8.zip').read_bytes()).stdout == b'archive payload\n'
with zipfile.ZipFile('traversal.zip', 'w') as z:
    z.writestr('../escaped.txt', b'escape')
result = subprocess.run([str(bin_dir / 'unzip'), '-o', 'traversal.zip', '-d', 'safe'], timeout=20, capture_output=True)
assert result.returncode in (0, 1)
assert not Path('escaped.txt').exists()
Path('broken.zip').write_bytes(b'PK\x03\x04broken')
assert subprocess.run([str(bin_dir / 'unzip'), '-t', 'broken.zip'], timeout=20, capture_output=True).returncode != 0
print('Stored, deflate, bzip2, ZIP64, extraction boundaries and corrupt-input rejection passed')
