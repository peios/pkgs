"""Fill gaps in upstream's manuals from the actual staged command interfaces."""
from pathlib import Path
import gzip, os, subprocess, sys
stage, version, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
descriptions = {
 'addr2line': 'translate addresses into source locations',
 'ar': 'create and inspect object archives',
 'elfcmp': 'compare ELF files',
 'elfcompress': 'change compression of ELF sections',
 'elflint': 'check ELF structural consistency',
 'findtextrel': 'locate text relocations in ELF objects',
 'make-debug-archive': 'create an offline debugging archive',
 'nm': 'list symbols in object files',
 'objdump': 'display information from ELF objects',
 'ranlib': 'update object archive indexes',
 'size': 'display object section sizes',
 'stack': 'display thread stack traces',
 'strings': 'print strings from object files',
 'strip': 'remove symbols and debug information from ELF files',
 'unstrip': 'combine stripped objects and separate debugging information',
}
env = dict(os.environ, LC_ALL='C', LD_LIBRARY_PATH=str(stage/'usr/lib/x86_64-linux-peios'))
def roff(text):
 return '\n'.join('\\&'+line.replace('\\','\\e').replace('-','\\-') for line in text.splitlines())
output.mkdir(parents=True, exist_ok=True)
for suffix, description in descriptions.items():
 name='eu-'+suffix;binary=stage/'usr/bin'/name
 help_text=subprocess.check_output([str(binary),'--help'],text=True,env=env).replace(str(binary),name)
 if not help_text.startswith('Usage:') or len(help_text)<100:
  raise SystemExit('Unexpected command help: '+name)
 extra=''
 if suffix == 'make-debug-archive':
  extra='''\n.SH ENVIRONMENT
UNSTRIP and AR select the elfutils helper commands. TMPDIR selects the scratch
directory. SUDO selects an optional privilege helper used only with --sudo;
install and authorize that helper separately before requesting this mode.
'''
 page=f'''.TH {name.upper()} 1 "" "elfutils {version}" "User Commands"
.SH NAME
{name} \\- {description}
.SH SYNOPSIS
.B {name}
.RI [ options ] " " [ operands ... ]
.SH DESCRIPTION
This command is part of elfutils, the ELF and DWARF inspection and
manipulation tools. The following interface is obtained from the packaged
executable. Input selection and option availability are version specific.
.SH OPTIONS
.nf
{roff(help_text)}
.fi
{extra}
.SH SEE ALSO
.BR eu-readelf (1),
.BR eu-elfclassify (1)
'''
 (output/(name+'.1.gz')).write_bytes(gzip.compress(page.encode(),compresslevel=9,mtime=0))
