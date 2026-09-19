#!/usr/bin/env python3
"""Exercise installed Ninja shell rules; closure mode requires /bin absent."""
from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--ninja',type=Path,required=True)
p.add_argument('--work',type=Path,required=True)
p.add_argument('--require-no-bin',action='store_true')
p.add_argument('--root',type=Path,help='Host-side closure check: read-only root containing the declared shell and ELF runtime')
a=p.parse_args();binary=a.ninja.resolve(strict=True);work=a.work.resolve()
root=a.root.resolve(strict=True) if a.root else Path('/')
assert os.access(root/'usr/bin/sh',os.X_OK),'Declared POSIX shell is unavailable'
if a.require_no_bin:assert not os.path.lexists(root/'bin'),'This gate requires a root with no /bin alias'
work.mkdir(parents=True,exist_ok=False)
(work/'build.ninja').write_text('''rule normal
  command = value=normal; printf '%s\\n' "$$value" > "$out"
rule console
  command = printf 'console\\n' > "$out"
  pool = console
rule failure
  command = printf 'intentional-shell-failure\\n' >&2; exit 37
build normal.out: normal
build console.out: console
build fail: failure
default normal.out console.out
''')
results=[]
def run(name,args,code):
 command=[str(binary),'-C',str(work),'-v',*args]
 if a.root:
  command=['bwrap','--die-with-parent','--unshare-all','--new-session','--ro-bind',str(root),'/', '--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(binary),'/tmp/ninja-under-test','--bind',str(work),'/tmp/ninja-shell-work','--chdir','/tmp/ninja-shell-work','--clearenv','--setenv','PATH','/usr/bin','--','/tmp/ninja-under-test','-C','/tmp/ninja-shell-work','-v',*args]
 child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,text=True)
 try:output,_=child.communicate(timeout=30)
 except subprocess.TimeoutExpired:
  os.killpg(child.pid,signal.SIGKILL);output,_=child.communicate();raise AssertionError('Ninja shell regression timed out: '+output)
 (work/(name+'.log')).write_text(output)
 results.append({'name':name,'command':command,'returncode':child.returncode,'log_sha256':hashlib.sha256(output.encode()).hexdigest()})
 assert child.returncode==code,(name,child.returncode,output)
 return output
run('normal-and-console',[],0)
assert (work/'normal.out').read_text()=='normal\n'
assert (work/'console.out').read_text()=='console\n'
output=run('failed-shell-rule',['fail'],37)
assert 'intentional-shell-failure' in output and 'posix_spawn' not in output
assert not (work/'fail').exists()
record={'passed':True,'ninja_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'root':str(root),'bin_absent':not os.path.lexists(root/'bin'),'require_no_bin':a.require_no_bin,'results':results}
(work/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
