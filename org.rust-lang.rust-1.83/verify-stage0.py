#!/usr/bin/env python3
"""Recheck the acquired authenticated binary bytes inside each offline worker."""
from pathlib import Path
import hashlib,json,sys
vendor=Path(sys.argv[1]);root=vendor/'stage0'
expected=json.loads((vendor/'stage0-byte-identities.json').read_text())
actual={}
for p in root.rglob('*'):
    if not p.is_file():continue
    with p.open('rb') as stream:
        magic=stream.read(8)
        if not (magic.startswith(b'\x7fELF') or magic==b'!<arch>\n'):continue
        stream.seek(0);actual[str(p.relative_to(root))]=hashlib.file_digest(stream,'sha256').hexdigest()
if len(actual)<10 or actual!=expected:
    raise SystemExit('private bootstrap binary identity mismatch')
print('Verified',len(actual),'unchanged authenticated bootstrap ELF/archive files')
