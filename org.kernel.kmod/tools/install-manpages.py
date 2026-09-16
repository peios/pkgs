descriptions={'kmod': ('manage kernel modules', ''), 'depmod': ('generate kernel module dependency indexes', ''), 'insmod': ('insert a kernel module', ''), 'lsmod': ('list loaded kernel modules', ''), 'modinfo': ('display kernel module metadata', ''), 'modprobe': ('load and remove modules with dependencies', ''), 'rmmod': ('remove kernel modules', '')}
section='8'
family='org.kernel.kmod'
extra='Configuration syntax and detailed upstream documentation are installed in\n/usr/share/doc/org.kernel.kmod/upstream-manuals.\n.SH SEE ALSO\n.BR modprobe (8),\n.BR depmod (8)'
from pathlib import Path
import gzip,os,subprocess,sys
stage,version,dest=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
def roff(text):return '\n'.join('\\&'+l.replace('\\','\\e').replace('-','\\-') for l in text.splitlines())
env=dict(os.environ,LC_ALL='C',LD_LIBRARY_PATH=str(stage/'usr/lib/x86_64-linux-peios'))
dest.mkdir(parents=True,exist_ok=True)
for name,(description,static) in descriptions.items():
 binary=stage/('usr/libexec' if name=='depmod' else 'usr/bin')/name
 text=static or subprocess.check_output([str(binary),'--help'],env=env,text=True).replace(str(binary),name)
 assert len(text)>15,name
 page=f'.TH {name.upper()} {section} "" "{family} {version}" "User Commands"\n.SH NAME\n{name} \\- {description}\n.SH SYNOPSIS\n.nf\n{roff(text)}\n.fi\n.SH DESCRIPTION\n{description}.\n{extra}\n'
 (dest/(name+'.'+section+'.gz')).write_bytes(gzip.compress(page.encode(),mtime=0))
