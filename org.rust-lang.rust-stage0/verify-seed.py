from pathlib import Path
import hashlib,os,sys
source,stage=map(Path,sys.argv[1:])
components=[source/n for n in ('rustc','cargo','rust-std-x86_64-unknown-linux-gnu')]
count=0
for p in stage.rglob('*'):
 if not p.is_file():continue
 with p.open('rb') as f:magic=f.read(8)
 if not (magic.startswith(b'\x7fELF') or magic==b'!<arch>\n'):continue
 rel=p.relative_to(stage);candidates=[c/rel for c in components if (c/rel).is_file()]
 assert candidates,rel
 def sha(q):
  with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
 expected={sha(q) for q in candidates};assert len(expected)==1 and sha(p) in expected,rel
 count+=1
assert count>=10,count
print('Verified original upstream bytes for',count,'seed ELF/archive files')
