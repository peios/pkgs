#!/usr/bin/env python3
"""Install command references from the exact staged Docutils CLIs."""
import gzip
import os
from pathlib import Path
import subprocess
import sys

stage = Path(sys.argv[1]).resolve()
site = sys.argv[2]
version = sys.argv[3]
man = stage / "usr/share/man/man1"
man.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONPATH=site, PYTHONDONTWRITEBYTECODE="1")
for command in sorted((stage / "usr/bin").iterdir()):
    help_text = subprocess.check_output([str(command), "--help"], env=env, cwd=stage, text=True)
    assert "--help" in help_text and "--version" in help_text, command.name
    # Literal help text must not become roff requests or escape sequences.
    lines = [line.replace("\\", r"\e") for line in help_text.splitlines()]
    literal = "\n".join((r"\&" + line) if line.startswith((".", "'")) else line for line in lines)
    text = (f'.TH "{command.name.upper()}" 1 "" "Docutils {version}" "User Commands"\n'
            f'.SH NAME\n{command.name} \\- process reStructuredText documents\n'
            '.SH DESCRIPTION\nThis command reference is generated from the installed Docutils program.\n'
            '.SH OPTIONS\n.nf\n' + literal + '\n.fi\n')
    (man / (command.name + ".1.gz")).write_bytes(gzip.compress(text.encode(), mtime=0))
