"""Report exact upstream cases unavailable in this worker's kernel identity view."""
import os,sys
from pathlib import Path
excluded=[]
def mapped(kind, identity):
 p=Path('/proc/self/'+kind+'_map')
 if not p.exists():return True
 return any(start <= identity < start+length for start,outer,length in (map(int,line.split()) for line in p.read_text().splitlines()))
def unavailable(names, reason):
 print('Uncovered: '+reason+': '+','.join(names),file=sys.stderr);excluded.extend(names)
if any(not mapped('gid',g) for g in os.getgroups()):
 unavailable(['chgrp','daemon-groupmap-wild','dir-sgid','ownership-depth'], 'supplementary group IDs are not mapped into the worker namespace')
if not mapped('uid',5001):
 unavailable(['protected-regular'], 'fixture UID 5001 is not mapped into the worker namespace')
if os.path.islink('/proc/self') and os.lstat('/proc/self').st_uid not in (0,os.geteuid()):
 unavailable(['rrsync-backup-dir-inband-pivot','rrsync-pull-delivers-content'], 'kernel /proc/self symlink owner is unmapped; the ownership guard correctly refuses it')
print(','.join(excluded))
