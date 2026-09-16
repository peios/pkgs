import hashlib,io,json,subprocess,sys,tarfile
from pathlib import Path
recipe=Path(sys.argv[1]); output=Path(sys.argv[2]); provenance=json.loads((recipe/'provenance.json').read_text())
archive=recipe/'libpeios-source.peipkg'
with archive.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=provenance['archive_sha256']:
        raise SystemExit('reference libpeios source does not match authenticated package')
# zstd is declared acquisition tooling; source bytes are authenticated above.
raw=subprocess.check_output(['zstd','-q','-d','-c',str(archive)])
with tarfile.open(fileobj=io.BytesIO(raw)) as package:
    name='usr/src/dist/dev.peios.libpeios-0.5.0-1/upstream/dev.peios.libpeios-0.5.0-1.tar'
    data=package.extractfile(name).read()
if hashlib.sha256(data).hexdigest()!=provenance['upstream_tar_sha256']:
    raise SystemExit('reference libpeios embedded source changed')
with tarfile.open(fileobj=io.BytesIO(data)) as upstream:
    upstream.extractall(output,filter='data')
if sorted(x.name for x in output.iterdir())!=['dev.peios.libpeios-0.5.0-1']:
    raise SystemExit('unexpected reference libpeios source layout')

# Wrapper commands must remain the unchanged commands from authenticated source.
import tomllib
metadata=tomllib.loads((output/'dev.peios.libpeios-0.5.0-1/pekit.toml').read_text(encoding='utf-8'))
for script,target in [('vendor.sh','vendor'),('build.sh','main')]:
    if (recipe/script).read_text(encoding='utf-8')!=metadata['build'][target]['command']:
        raise SystemExit('reference wrapper drifted from authenticated source: '+script)
