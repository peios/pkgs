"""Generate version-matched command references from the installed LLVM tools.

Use the executable interface, including Windows and subcommand drivers, rather
than requiring Sphinx and its themes in the bootstrap toolchain. The signed
upstream command-guide sources are also installed for the longer explanations.
"""
from pathlib import Path
import gzip
import os
import re
import shutil
import subprocess
import sys

stage, source, version, output = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
env = dict(os.environ, LC_ALL='C', LD_LIBRARY_PATH=str(stage/'usr/lib/x86_64-linux-peios'))
special = {
    'clang-cl': ['-help'], 'lld-link': ['-help'],
    'llvm-cvtres': ['/?'], 'llvm-mt': ['/?'], 'llvm-rc': ['/?'],
    'llvm-ml': ['/?'], 'llvm-ml64': ['/?'], 'llvm-lto2': ['run', '--help'],
}
usage_exit = {'c-index-test', 'diagtool', 'lld', 'llvm-c-test', 'llvm-dlltool'}
descriptions = {
    'c-index-test': 'exercise the Clang indexing API',
    'clang-check': 'check C and C++ source with Clang',
    'clang-extdef-mapping': 'map external definitions for cross-translation-unit analysis',
    'clang-linker-wrapper': 'link host and offload device images',
    'clang-rename': 'rename symbols in C and C++ source',
    'clang-repl': 'interactively compile and execute C++',
    'clang-scan-deps': 'scan compiler dependencies',
    'diagtool': 'inspect Clang diagnostics and warning groups',
    'lld': 'select an LLVM linker driver',
    'ld.lld': 'link ELF objects',
    'ld64.lld': 'link Mach-O objects',
    'lld-link': 'link PE/COFF objects',
    'wasm-ld': 'link WebAssembly objects',
    'llvm-c-test': 'exercise the LLVM C API',
    'reduce-chunk-list': 'minimize an interesting integer-interval list',
    'llvm-debuginfod': 'serve debug artifacts over the debuginfod protocol',
    'llvm-dlltool': 'create Windows import libraries',
    'llvm-jitlink': 'link and execute object files with JITLink',
    'llvm-rtdyld': 'link and execute object files with RuntimeDyld',
    'llvm-undname': 'demangle Microsoft C++ symbol names',
}

def roff(text):
    return '\n'.join('\\&'+line.replace('\\', '\\e').replace('-', '\\-') for line in text.splitlines())

for binary in sorted((stage/'usr/bin').iterdir()):
    name = binary.name
    # This upstream driver has no standalone help response. Its maintained
    # reference covers the actual source option table and input format.
    if name == 'clang-installapi':
        template = Path(__file__).parent/'man/clang-installapi.1'
        page = template.read_text().replace('@LLVM_VERSION@', version)
        dest = output/'clang/usr/share/man/man1/clang-installapi.1.gz'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(gzip.compress(page.encode(), compresslevel=9, mtime=0))
        continue
    args = special.get(name, ['--help'])
    result = subprocess.run([str(binary), *args], env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=30)
    text = (result.stdout + result.stderr).replace(str(binary), name).strip()
    expected = 1 if name in usage_exit else 0
    if result.returncode != expected or len(text) < 100:
        raise SystemExit(f'Unexpected {name} help interface: {result.returncode}: {text}')
    if str(stage) in text:
        raise SystemExit('Build path leaked into command documentation: '+name)
    guide = source/'llvm/docs/CommandGuide'/(name+'.rst')
    description = descriptions.get(name)
    if description is None and guide.exists():
        title = guide.read_text().splitlines()[0]
        if title.startswith(name+' - '):
            description = title[len(name)+3:]
    if description is None:
        overview = re.search(r'^OVERVIEW:\s*(\S[^\n]+)', text, re.M)
        if overview:
            description = overview.group(1).rstrip('. ')
    if not description or description == name:
        raise SystemExit('Missing meaningful command description: '+name)
    component = 'llvm'
    if name == 'llvm-config':
        component = 'llvm-devel'
    elif name.startswith('clang') or name in {'c-index-test', 'diagtool'}:
        component = 'clang'
    elif name in {'lld', 'ld.lld', 'ld64.lld', 'lld-link', 'wasm-ld'}:
        component = 'lld'
    intro = ''
    if name == 'lld':
        intro = 'Select ld.lld for ELF, ld64.lld for Mach-O, lld-link for PE/COFF,\nor wasm-ld for WebAssembly. The generic driver itself does not link input.\n'
    elif name == 'llvm-lto2':
        intro = 'Use the run subcommand for resolution-based link-time optimization.\nUse dump-symtab followed by bitcode files to inspect their LTO symbol tables.\nThe option reference below describes run.\n'
    page = f''' .TH {name.upper()} 1 "" "LLVM {version}" "User Commands"
.SH NAME
{roff(name+' - '+description)}
.SH SYNOPSIS
.B {name}
.RI [ options ] " " [ operands ... ]
.SH DESCRIPTION
{intro}The following interface is generated from the packaged LLVM {version}
executable. Option availability and accepted input formats are version specific.
.SH OPTIONS
.nf
{roff(text)}
.fi
.SH DOCUMENTATION
The org.llvm.llvm package supplies the upstream command-guide sources at
/usr/share/doc/org.llvm.llvm/CommandGuide. The LLVM, Clang and LLD manuals
are also available at https://releases.llvm.org/{version}/docs/,
https://releases.llvm.org/{version}/tools/clang/docs/ and
https://releases.llvm.org/{version}/tools/lld/docs/ respectively.
'''.lstrip()
    dest = output/component/'usr/share/man/man1'/(name+'.1.gz')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(gzip.compress(page.encode(), compresslevel=9, mtime=0))
