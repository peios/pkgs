import gzip, re, sys
from pathlib import Path
from docutils.core import publish_string
text=Path(sys.argv[1]).read_text()
text=re.sub(r'^\.\. (?:highlight|iscman|program)::.*\n', '', text, flags=re.M)
text=re.sub(r':(?:program|option|iscman|ref|doc):`([^`]+)`', r'``\1``', text)
text=re.sub(r'^\.\. option:: (.*)$', r'``\1``', text, flags=re.M)
text=text.replace('|named_version|', 'BIND 9')
text=text.replace('dig - DNS lookup utility\n------------------------', 'dig\n===\n\nDNS lookup utility\n\n:Manual section: 1\n:Manual group: Network tools')
data=publish_string(text,writer_name='manpage', settings_overrides={'halt_level':2,'report_level':2})
with open(sys.argv[2], 'wb') as f:
    with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as z: z.write(data)
