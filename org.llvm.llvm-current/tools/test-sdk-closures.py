#!/usr/bin/env python3
"""Exercise each declared SDK split without borrowing files from sibling splits."""
from pathlib import Path
import errno
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib

recipe, stage, output = map(lambda s: Path(s).resolve(), sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
packages = {}
for manifest in sorted(recipe.glob('*.package.pekit.toml')):
    data = tomllib.loads(manifest.read_text())
    packages[data['package']['name']] = data

def closure(name, visiting=()):
    if name in visiting:
        raise ValueError('Package dependency cycle: ' + ' -> '.join((*visiting, name)))
    found = {name}
    for dependency in packages[name].get('dependencies', {}):
        if dependency in packages:
            found |= closure(dependency, (*visiting, name))
    return found

def mapped_files(name):
    data = packages[name]
    for pattern, destination in data.get('files', {}).items():
        if pattern.startswith('@source:'):
            continue  # Source license files do not affect an installed SDK consumer.
        assert pattern.startswith(':'), pattern
        pattern = pattern[1:]
        wildcard = any(c in pattern for c in '*?[')
        matches = sorted(stage.glob(pattern)) if wildcard else [stage / pattern]
        if not matches:
            raise ValueError('Unmatched package mapping: ' + pattern)
        first = next((i for i, c in enumerate(pattern) if c in '*?['), len(pattern))
        prefix = pattern[:first].rsplit('/', 1)[0] if wildcard else ''
        for path in matches:
            if not path.is_file() and not path.is_symlink():
                continue
            relative = path.relative_to(stage).as_posix()
            if any(fnmatch.fnmatch(':' + relative, x) for x in data.get('excludes', [])):
                continue
            target = Path(destination) / path.relative_to(stage / prefix) if wildcard else Path(destination)
            assert not target.is_absolute() and '..' not in target.parts, target
            yield path, target

results = []
for family in ('llvm', 'clang', 'lld'):
    selected = closure('org.llvm.' + family + '-devel')
    assert 'org.llvm.llvm-static' not in selected
    work = output / family
    work.mkdir()
    root = work / 'root'
    owners = {}
    for name in sorted(selected):
        for source, relative in mapped_files(name):
            key = relative.as_posix()
            if key in owners:
                raise ValueError('Cross-package file collision: ' + key)
            owners[key] = name
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                target.symlink_to(os.readlink(source))
            else:
                try:
                    os.link(source, target)
                except OSError as error:
                    if error.errno != errno.EXDEV:
                        raise
                    shutil.copy2(source, target)
    (work / 'ownership.json').write_text(json.dumps(owners, sort_keys=True, indent=2) + '\n')
    prefix = root / 'usr'
    cmake = prefix / 'lib/x86_64-linux-peios/cmake'
    args = ['cmake', '-S', str(recipe / 'tools/sdk-consumers'), '-B', str(work / 'build'), '-G', 'Ninja',
            '-DSDK_FAMILY=' + family, '-DLLVM_DIR=' + str(cmake / 'llvm'),
            '-DCMAKE_PREFIX_PATH=' + str(prefix), '-DCMAKE_IGNORE_PREFIX_PATH=' + str(stage / 'usr'),
            '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF']
    if family == 'clang':
        args += ['-DClang_DIR=' + str(cmake / 'clang')]
    elif family == 'lld':
        args += ['-DLLD_DIR=' + str(cmake / 'lld')]
    # LLVM18 public headers need this standard include with GCC16 (same bridge
    # as the compiler build); this does not alter the source or SDK ownership.
    if os.environ['PEKIT_VERSION'].startswith('18.'):
        args += ['-DCMAKE_CXX_FLAGS=' + os.environ.get('CXXFLAGS', '') + ' -include cstdint']
    env = os.environ.copy()
    env.pop('LD_LIBRARY_PATH', None)
    env.pop('CMAKE_PREFIX_PATH', None)
    with (work / 'consumer.log').open('w') as log:
        for command in (args, ['cmake', '--build', str(work / 'build'), '--parallel', '2'],
                        ['ctest', '--test-dir', str(work / 'build'), '--output-on-failure']):
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    if family == 'llvm':
        subprocess.run([sys.executable, str(recipe / 'tools/test-llvm-config.py'), str(prefix),
                        str(recipe / 'tools/sdk-consumers/llvm-consumer.cpp'), str(work / 'llvm-config')],
                       env=env, check=True)
    results.append({'sdk': family, 'packages': sorted(selected), 'files': len(owners),
                    'ownership_sha256': hashlib.sha256((work / 'ownership.json').read_bytes()).hexdigest(),
                    'passed': True})
    # Keep the manifest inventory and consumer evidence, not three large SDK copies.
    shutil.rmtree(root)
(output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print('LLVM, Clang and LLD declared SDK closures passed CMake and linked consumers')
