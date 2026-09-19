"""Exercise installed llvm-config from the declared SDK's relocated prefix."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys

prefix, source, work = map(lambda value: Path(value).resolve(), sys.argv[1:])
work.mkdir(parents=True, exist_ok=True)
tool = prefix / 'bin/llvm-config'
env = os.environ.copy()
env.pop('LD_LIBRARY_PATH', None)

def query(*args):
    return subprocess.check_output([str(tool), *args], env=env, text=True).strip()

libdir = prefix / 'lib/x86_64-linux-peios'
queries = {}
for option, expected in [('prefix', prefix), ('includedir', prefix / 'include'),
                         ('libdir', libdir), ('cmakedir', libdir / 'cmake/llvm'),
                         ('obj-root', prefix)]:
    actual = query('--' + option)
    assert actual == str(expected), (option, actual, str(expected))
    queries[option] = actual
assert query('--version') == os.environ['PEKIT_VERSION']
results = []
with (work / 'consumer.log').open('w') as log:
    for mode in ('shared', 'static'):
        flags = shlex.split(query('--cxxflags'))
        if os.environ['PEKIT_VERSION'].startswith('18.'):
            flags += ['-include', 'cstdint']
        libs = shlex.split(query('--link-' + mode, '--ldflags', '--libs', '--system-libs', 'core'))
        output = work / ('llvm-config-' + mode)
        command = shlex.split(os.environ.get('CXX', 'c++')) + shlex.split(os.environ.get('CXXFLAGS', '')) + flags
        command += [str(source), '-o', str(output)] + libs + ['-Wl,-rpath,' + str(libdir)]
        log.write(shlex.join(command) + '\n'); log.flush()
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(output)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        dynamic = subprocess.check_output(['readelf', '-d', str(output)], env=env, text=True)
        needs_llvm = any('NEEDED' in line and 'libLLVM' in line for line in dynamic.splitlines())
        assert needs_llvm == (mode == 'shared'), (mode, dynamic)
        results.append({'mode': mode, 'arguments': libs, 'passed': True, 'needs_shared_llvm': needs_llvm})
(work / 'results.json').write_text(json.dumps({'queries': queries, 'consumers': results}, indent=2) + '\n')
