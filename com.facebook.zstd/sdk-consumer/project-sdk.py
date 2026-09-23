#!/usr/bin/env python3
"""Project only the selected SDK's declared same-family payload closure."""
from pathlib import Path
import argparse,hashlib,json,shutil,tomllib
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--recipe',type=Path,required=True);p.add_argument('--stage',type=Path,required=True)
p.add_argument('--sdk',required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.recipe=a.recipe.resolve();a.stage=a.stage.resolve();a.out=a.out.resolve()
if a.out.exists():raise SystemExit('SDK projection output must be fresh')
packages={}
for f in a.recipe.glob('*.package.pekit.toml'):
 d=tomllib.loads(f.read_text());packages[d['package']['name']]=d
selected=set();external=set()
def visit(name,stack=()):
 if name in stack:raise ValueError('package dependency cycle')
 if name in selected:return
 selected.add(name)
 for dep,constraint in packages[name].get('dependencies',{}).items():
  if dep in packages:
   if constraint!='= {{release}}':raise ValueError('SDK family dependency must select exact matching revision')
   visit(dep,stack+(name,))
  else:external.add(dep)
visit(a.sdk)
if any(name.endswith('-static') for name in selected):raise ValueError('SDK unexpectedly requires optional static umbrella')
a.out.mkdir(parents=True)
files={}
for name in sorted(selected):
 d=packages[name]
 if d.get('excludes'):raise ValueError('projection needs explicit support for package excludes')
 for source,destination in d['files'].items():
  if source.startswith('@source:'):continue # Licences do not affect this SDK consumer projection.
  if not source.startswith(':usr/'):raise ValueError('unsupported SDK payload input '+source)
  pattern=source[1:];wild=any(c in pattern for c in '*?[')
  parts=Path(pattern).parts
  base=Path(*parts[:next((i for i,x in enumerate(parts) if any(c in x for c in '*?[')),len(parts))]) if wild else None
  matches=list(a.stage.glob(pattern)) if wild else [a.stage/pattern]
  if not matches:raise ValueError('declared SDK payload missing: '+pattern)
  expanded=[]
  for f in matches:
   expanded.extend(f.rglob('*') if f.is_dir() and not f.is_symlink() else [f])
  for f in expanded:
   if f.is_dir() and not f.is_symlink():continue
   rel=f.relative_to(a.stage)
   mapped=Path(destination)/rel.relative_to(base) if wild else Path(destination)
   if mapped!=rel:raise ValueError('unsupported non-identity SDK payload mapping '+str(rel))
   target=a.out/rel;target.parent.mkdir(parents=True,exist_ok=True)
   if str(rel) in files:continue
   if f.is_symlink():
    target.symlink_to(f.readlink());record={'owner':name,'symlink':str(f.readlink())}
   else:
    shutil.copy2(f,target)
    with target.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    record={'owner':name,'sha256':sha}
   files[str(rel)]=record
for path,record in files.items():
 if 'symlink' in record:
  target=(a.out/path).resolve(strict=True)
  if not target.is_relative_to(a.out):raise ValueError('projected SDK link escapes its package closure')
(a.out/'projection.json').write_text(json.dumps({'sdk':a.sdk,'packages':sorted(selected),'external_packages':sorted(external),'files':files},indent=2)+'\n')
print('SDK_PROJECTION '+json.dumps({'sdk':a.sdk,'packages':sorted(selected),'files':len(files)},sort_keys=True))
