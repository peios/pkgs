from pathlib import Path
import hashlib,sys
source,stage=map(Path,sys.argv[1:]);count=0
for directory in ('bin','pkg/tool/linux_amd64'):
 for p in (stage/directory).iterdir():
  if not p.is_file():continue
  original=source/p.relative_to(stage)
  def sha(q):
   with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
  assert original.is_file() and sha(original)==sha(p),p
  count+=1
assert count==20,count
print('Verified all 20 original Go bootstrap executables')
