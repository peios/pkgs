#!/usr/bin/env python3
"""install-manpages: generate minimal manual pages from --help (PEI-1163).

    install-manpages.py STAGE VERSION DEST SPEC

For upstreams that ship no manual pages for some commands, write one gzipped
roff page per command into DEST. The SYNOPSIS is the command's own --help
output (run from STAGE, with STAGE's library directory on LD_LIBRARY_PATH),
or a fixed synopsis where --help is not usable. Output is deterministic:
LC_ALL=C, gzip mtime 0.

SPEC is a JSON file:

    {
      "family":  "org.example.thing",   # shown in the page footer with VERSION
      "section": "1",
      "extra":   "roff appended after DESCRIPTION (may be empty)",
      "commands": {
        "name": {
          "description": "one-line summary",
          "synopsis":    "fixed synopsis; omit to run --help",
          "path":        "usr/libexec/name; default usr/bin/<name>"
        }
      }
    }

Commands are written in SPEC order.
"""
from pathlib import Path
import gzip
import json
import os
import subprocess
import sys

if len(sys.argv) != 5:
    sys.exit('usage: install-manpages.py STAGE VERSION DEST SPEC')
stage, version, dest = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
spec = json.loads(Path(sys.argv[4]).read_text())
section = spec['section']
family = spec['family']
extra = spec.get('extra', '')


def roff(text):
    return '\n'.join('\\&' + l.replace('\\', '\\e').replace('-', '\\-')
                     for l in text.splitlines())


env = dict(os.environ, LC_ALL='C',
           LD_LIBRARY_PATH=str(stage / 'usr/lib/x86_64-linux-peios'))
dest.mkdir(parents=True, exist_ok=True)
for name, command in spec['commands'].items():
    description = command['description']
    binary = stage / command.get('path', 'usr/bin/' + name)
    text = command.get('synopsis') or subprocess.check_output(
        [str(binary), '--help'], env=env, text=True).replace(str(binary), name)
    assert len(text) > 15, name
    page = (f'.TH {name.upper()} {section} "" "{family} {version}" "User Commands"\n'
            f'.SH NAME\n{name} \\- {description}\n'
            f'.SH SYNOPSIS\n.nf\n{roff(text)}\n.fi\n'
            f'.SH DESCRIPTION\n{description}.\n{extra}\n')
    (dest / f'{name}.{section}.gz').write_bytes(gzip.compress(page.encode(), mtime=0))
