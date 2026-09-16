descriptions={'codiff': ('compare type and function information in object files', ''), 'ctracer': ('generate tracing support from debugging information', ''), 'dtagnames': ('print DWARF tag names', 'dtagnames FILE ...'), 'pdwtags': ('print DWARF tags', ''), 'pglobal': ('display global symbols and their debugging information', ''), 'prefcnt': ('display type reference information', 'prefcnt FILE ...'), 'scncopy': ('copy selected ELF sections', ''), 'syscse': ('inspect debugging information for system call structures', ''), 'btfdiff': ('compare DWARF and BTF type layouts', 'btfdiff DWARF_FILE [BTF_FILE]\nPAHOLE selects the pahole executable.'), 'fullcircle': ('compare original and regenerated type information', 'fullcircle FILE\nPFUNCT and CODIFF select the helper executables.\nThe helper compiles regenerated C with gcc.')}
section='1'
family='org.kernel.pahole'
extra='Additional upstream documentation is installed in /usr/share/doc/org.kernel.pahole.\n.SH SEE ALSO\n.BR pahole (1),\n.BR pfunct (1)'
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
