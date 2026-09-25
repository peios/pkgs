#!/usr/bin/env python3
"""Freeze signed repository metadata once per job; archives remain immutable."""
import fcntl
import os
from pathlib import Path
import shutil
import tempfile

state = Path(os.environ['PEKIT_JOB_STATE'])
# The publish target in package.pekit.toml; keep the two in step.
source = (Path(os.environ['PEKIT_WORKSPACE_ROOT']) / '_repo2_').resolve()
snapshot = state / 'native-repository'
if not snapshot.exists():
    temporary = Path(tempfile.mkdtemp(prefix='repository-', dir=state))
    try:
        # peipkg-repo publish holds an exclusive flock on .peipkg-repo.json
        # while it rewrites the descriptor and indexes. A shared lock here
        # waits for a publish in progress, so the copied index and its
        # signature always belong to the same generation.
        with open(source / '.peipkg-repo.json', 'rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            for name in ('repo.json', 'repo.json.sig', '.peipkg-repo.json'):
                shutil.copy2(source / name, temporary / name)
            shutil.copytree(source / 'index', temporary / 'index')
            shutil.copytree(source / 'keys', temporary / 'keys')
        (temporary / 'p').symlink_to(source / 'p', target_is_directory=True)
        temporary.rename(snapshot)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
print(snapshot)
