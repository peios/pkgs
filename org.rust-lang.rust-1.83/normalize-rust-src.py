#!/usr/bin/python3
"""Normalize the installed Rust 1.83 Unicode generator to its required Python 3."""
import os
from pathlib import Path
import stat
import sys
import tempfile

root = Path(sys.argv[1])
script = root / "library/core/src/unicode/printable.py"
if script.is_symlink() or not script.is_file():
    raise SystemExit(f"rust-src: expected regular Unicode generator: {script}")
original = script.read_bytes()
first, separator, body = original.partition(b"\n")
if first not in (b"#!/usr/bin/env python", b"#!/usr/bin/python3", b"#!/bin/python3") or not separator:
    raise SystemExit(f"rust-src: unexpected Unicode generator interpreter: {first!r}")
# Name the interpreter through the runtime view, as every installed script does.
normalized = b"#!/bin/python3\n" + body
if normalized != original:
    # Rust's installer may use hard links. Replace this installed entry atomically,
    # so normalizing its interpreter cannot mutate the original source capture.
    mode = stat.S_IMODE(script.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".pekit-python3-", dir=script.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(normalized)
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, script)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
