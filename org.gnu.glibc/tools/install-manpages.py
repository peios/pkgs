#!/usr/bin/env python3
"""Install command manuals from the staged glibc's own help, plus Peios notes.

The descriptions and integration notes are maintained here; option references
come from the exact binaries being packaged, without an extra host toolchain.
SPDX-License-Identifier: LGPL-2.1-or-later
"""
import gzip
import os
from pathlib import Path
import subprocess
import sys

stage = Path(sys.argv[1]).resolve()
version = sys.argv[2]
out = Path(sys.argv[3]) if len(sys.argv) > 3 else stage
libdir = stage / 'usr/lib/x86_64-linux-peios'
loader = libdir / 'ld-linux-x86-64.so.2'
# name: (section, one-line description, integration notes)
commands = {
    'gencat': ('1', 'compile message catalogs', 'Compile message-definition files into the catalog consumed by catopen and catgets. Input may contain multiple message sets.'),
    'getconf': ('1', 'query system configuration values', 'Query a system-wide value or a value associated with a pathname. A reported limit can depend on the running kernel, filesystem and process environment.'),
    'getent': ('1', 'query the C library name-service databases', 'Peios fixes account and group lookups to its authority provider and host lookups to its resolver provider. Selecting a different service cannot override those databases. Traditional passwd files are not the Peios account authority; shadow and gshadow are deliberately empty.'),
    'iconv': ('1', 'convert text between character encodings', 'Read input files, or standard input when no file is specified, and write converted bytes. Additional legacy encodings require org.gnu.glibc-gconv-extra. GCONV_PATH selects converter directories.'),
    'iconvconfig': ('8', 'generate a character-conversion module cache', 'Generate the cache used to locate installed gconv converters. Use an explicit output or prefix when preparing a separate root; changing the system cache requires write access to its directory.'),
    'ld.so': ('8', 'load and run dynamically linked programs', 'The ELF interpreter loads the program and its shared dependencies. It can also be invoked directly with a program and its arguments. LD_LIBRARY_PATH, LD_PRELOAD and LD_AUDIT affect ordinary execution; secure-execution rules restrict these controls.'),
    'ldconfig': ('8', 'update shared-library links and cache', 'Inspect library directories, update shared-object links and generate the loader cache. The system configuration is /etc/ld.so.conf and the cache is /etc/ld.so.cache. Use the command options to inspect a cache or operate on a separate root.'),
    'ldd': ('1', 'display shared-library dependencies', 'Display the dependencies resolved by the dynamic loader for a program. For an untrusted file, use readelf -d to inspect its declared dependencies without running its interpreter.'),
    'locale': ('1', 'display locale settings and available locale data', 'Without operands, display the active locale categories. LC_ALL overrides individual LC_* categories, and LANG supplies their fallback. Installed locale packages determine which named locales are available.'),
    'localedef': ('1', 'compile locale definitions', 'Compile locale source and a character map into binary locale data. A path output name creates a locale directory; archive options manage a locale archive. Peios language packages install separate locale directories.'),
    'makedb': ('1', 'create or inspect a name-service database', 'Build a simple key-value database from text, or inspect a database with the undo option. These legacy database files do not override the fixed Peios account or host providers.'),
    'sln': ('8', 'create symbolic links with a statically linked tool', 'Create a link from a source and destination operand, or process a file containing source/destination pairs. The static program can be used when the dynamic loader is unavailable. It changes only the explicitly named links.'),
    'tzselect': ('1', 'choose a time-zone setting interactively', 'Select a geographic time zone and print a TZ value. Selection does not install the value or change the system clock. Set TZ in the environment of programs that should use it; zone information must be installed separately.'),
    'zdump': ('1', 'display time-zone transitions', 'Display time-zone information and, with verbose or interval options, the transitions within the requested range. TZDIR can select a zoneinfo directory.'),
    'zic': ('8', 'compile time-zone source data', 'Compile time-zone rules into zoneinfo files. Use -d to choose an output directory when preparing packages or a separate root. Compiling data does not change the system clock.'),
    'mtrace': ('1', 'analyze allocation trace logs', 'Read an allocation trace and report unmatched allocations and other traced allocation errors. An optional executable enables address-to-source lookup with addr2line. The traced application must produce compatible mtrace records; current glibc tracing requires the matching malloc debug support library.'),
    'pcprofiledump': ('1', 'decode program-counter profiling data', 'Decode a data file produced by the matching libpcprofile profiling module. Use the profiling module explicitly for the program being measured; ordinary program execution does not create this data.'),
    'pldd': ('1', 'list shared objects loaded by a process', 'Inspect the shared objects loaded into the named process. Inspection is subject to the kernel permissions governing access to that process.'),
    'sotruss': ('1', 'trace shared-library calls', 'Run a program with the matching glibc audit module and trace calls crossing shared-object boundaries. Filters and output options are described below. Loader auditing is restricted during secure execution.'),
    'sprof': ('1', 'report shared-object profiling data', 'Read a shared object and its profiling data to report execution counts and call relationships. Profiles must match the library that produced them. The loader profiling controls include LD_PROFILE and LD_PROFILE_OUTPUT.'),
    'xtrace': ('1', 'trace program execution', 'Trace a program using the matching profiling support, or decode an existing data file with --data. Tracing executes the supplied program and inherits its environment and permissions.'),
}

def roff(text):
    text = text.replace('\\', r'\e').replace('-', r'\-')
    return '\n'.join((r'\&' + line if line.startswith(('.', "'")) else line) for line in text.splitlines())

env = os.environ.copy()
env['LC_ALL'] = 'C'
for name, (section, description, notes) in commands.items():
    path = stage / 'usr/bin' / name
    if name == 'ld.so':
        argv = [str(loader)]
    elif name == 'sln':
        argv = [str(path)]
    elif name == 'mtrace':
        argv = ['perl', str(path)]
    elif path.read_bytes().startswith(b'\x7fELF'):
        argv = [str(loader), '--library-path', str(libdir), str(path)]
    else:
        argv = ['bash', str(path)]
    result = subprocess.run(argv + ['--help'], env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=20, check=True)
    help_text = result.stdout.replace(str(path), name).replace(str(loader), 'ld.so')
    if name == 'ld.so':
        # The tail describes the build host's current hwcaps and cache search;
        # keep command syntax/options, not machine-dependent diagnostics.
        marker = '\nThis program interpreter self-identifies as:'
        if marker not in help_text:
            raise SystemExit('ld.so: help layout changed; review diagnostic boundary')
        help_text = help_text.split(marker, 1)[0]
    if not help_text.strip() or str(stage) in help_text:
        raise SystemExit(f'{name}: missing help or leaked staging path')
    page = f'.TH "{name.upper()}" "{section}" "" "GNU C Library {version}" "Peios Commands"\n'
    page += '.SH NAME\n' + roff(name + ' - ' + description) + '\n'
    page += '.SH DESCRIPTION\n' + roff(notes) + '\n'
    page += '.SH SYNOPSIS AND OPTIONS\n.nf\n' + roff(help_text) + '\n.fi\n'
    page += '.SH DOCUMENTATION\nThe GNU C Library reference manual is supplied by org.gnu.glibc-doc.\n'
    page += 'This option reference is generated from the matching installed command.\n'
    dest = out / 'usr/share/man' / ('man' + section) / (name + '.' + section + '.gz')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(gzip.compress(page.encode(), compresslevel=9, mtime=0))
print(f'Installed {len(commands)} command manuals')
