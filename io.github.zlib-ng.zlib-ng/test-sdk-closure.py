#!/usr/bin/env python3
"""Exercise each manifest-derived SDK closure without borrowing staged files.

Only same-family dependencies are projected. The worker supplies the declared
compiler and system libc, just as it does for other consumer gates.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

RECIPE = Path(__file__).resolve().parent
STAGE, WORK, SMOKE = (Path(arg).resolve() for arg in sys.argv[1:])
SOURCE = Path(os.environ['PEKIT_SOURCE_ROOT']).resolve()
FAMILY = 'io.github.zlib-ng.zlib-ng'
LIB = Path('usr/lib/x86_64-linux-peios')
MANIFESTS = {}
for path in sorted(RECIPE.glob('*.package.pekit.toml')):
    data = tomllib.loads(path.read_text())
    name = data['package']['name']
    if name in MANIFESTS:
        raise RuntimeError(f'duplicate package manifest: {name}')
    MANIFESTS[name] = data
if WORK.exists():
    raise RuntimeError(f'SDK gate requires a fresh output directory: {WORK}')
WORK.mkdir(parents=True)


def closure(name):
    members, external = set(), set()
    def visit(member):
        if member in members:
            return
        members.add(member)
        for dep in MANIFESTS[member].get('dependencies', {}):
            if dep in MANIFESTS:
                visit(dep)
            elif dep.startswith(FAMILY):
                raise RuntimeError(f'missing same-family dependency manifest: {dep}')
            else:
                external.add(dep)
    visit(name)
    return sorted(members), sorted(external)


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise RuntimeError(f'unsafe package path: {value}')
    return path


def project(name, root):
    members, external = closure(name)
    files = {}
    for member in members:
        for spec, dest in MANIFESTS[member].get('files', {}).items():
            if spec.startswith('@source:'):
                base, pattern = SOURCE, spec[len('@source:'):]
            elif spec.startswith(':'):
                base, pattern = STAGE, spec[1:]
            else:
                raise RuntimeError(f'unhandled package source selector: {spec}')
            safe_relative(pattern)
            destination = safe_relative(dest)
            # These manifests use exact files, flat globs, and recursive /**.
            # Reject any new form rather than accidentally testing a larger tree.
            if pattern.endswith('/**'):
                parent = base / pattern[:-3]
                matches = sorted(p for p in parent.rglob('*') if not p.is_dir() or p.is_symlink())
                pairs = [(p, destination / p.relative_to(parent)) for p in matches]
            elif any(c in pattern for c in '*?['):
                if any(c in str(Path(pattern).parent) for c in '*?['):
                    raise RuntimeError(f'unhandled nested package glob: {spec}')
                pairs = [(p, destination / p.name) for p in sorted(base.glob(pattern))]
            else:
                src = base / pattern
                pairs = [(src, destination / src.name if dest.endswith('/') else destination)]
            if not pairs:
                raise RuntimeError(f'empty manifest selection: {member}: {spec}')
            for src, relative in pairs:
                if not src.is_file() and not src.is_symlink():
                    raise RuntimeError(f'missing or non-file manifest input: {src}')
                if str(relative) in files:
                    raise RuntimeError(f'package collision: {relative}')
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target, follow_symlinks=False)
                files[str(relative)] = {
                    'package': member,
                    'source': spec,
                    'symlink': os.readlink(target) if target.is_symlink() else None,
                    'sha256': None if target.is_symlink() else hashlib.sha256(target.read_bytes()).hexdigest(),
                }
    for relative, record in files.items():
        path = root / relative
        if path.is_symlink():
            path.resolve(strict=True).relative_to(root)
    return {'members': members, 'external_dependencies_supplied_by_worker': external, 'files': files}


def command(argv, log, *, env=None, expected_failure=False):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    log.write_text(result.stdout)
    if (result.returncode == 0) == expected_failure:
        raise RuntimeError(f'unexpected exit {result.returncode}: {argv}\n{result.stdout}')
    return result


results = []
for suffix, config, shared, static, archive, soname, smoke in (
    ('-compat', 'ZLIB', 'ZLIB::ZLIB', 'ZLIB::ZLIBSTATIC', 'libz.a', 'libz.so.1', 'compat.c'),
    ('', 'zlib-ng', 'zlib-ng::zlib', 'zlib-ng::zlibstatic', 'libz-ng.a', 'libz-ng.so.2', 'native.c'),
):
    for sdk in ('-devel', '-static'):
        package = FAMILY + suffix + sdk
        area = WORK / package
        root = area / 'root'
        root.mkdir(parents=True)
        record = {'package': package, **project(package, root)}
        source = area / 'consumer'
        source.mkdir()
        shutil.copy2(SMOKE / smoke, source / 'consumer.c')
        # Exact config mode cannot use CMake's FindZLIB module, package registry,
        # the complete staging prefix, or another ABI's SDK to conceal a split.
        (source / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(sdk_consumer C)
find_package({config} REQUIRED CONFIG PATHS "${{SDK_ROOT}}/{LIB}/cmake/{config}" NO_DEFAULT_PATH)
foreach(target IN ITEMS {shared} {static})
  get_target_property(location "${{target}}" IMPORTED_LOCATION_RELWITHDEBINFO)
  file(REAL_PATH "${{location}}" resolved)
  cmake_path(IS_PREFIX SDK_ROOT "${{resolved}}" NORMALIZE inside)
  if(NOT inside)
    message(FATAL_ERROR "Imported target escapes projected SDK: ${{target}}: ${{resolved}}")
  endif()
  get_target_property(includes "${{target}}" INTERFACE_INCLUDE_DIRECTORIES)
  foreach(include IN LISTS includes)
    file(REAL_PATH "${{include}}" resolved)
    cmake_path(IS_PREFIX SDK_ROOT "${{resolved}}" NORMALIZE inside)
    if(NOT inside)
      message(FATAL_ERROR "Imported include escapes projected SDK: ${{resolved}}")
    endif()
  endforeach()
endforeach()
add_executable(consumer-shared consumer.c)
target_link_libraries(consumer-shared PRIVATE {shared})
add_executable(consumer-static consumer.c)
target_link_libraries(consumer-static PRIVATE {static})
''')
        def configure(build):
            return ['cmake', '-S', str(source), '-B', str(build),
                    f'-DSDK_ROOT={root}', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
                    '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF',
                    '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF']
        build = area / 'build'
        command(configure(build), area / 'configure.log')
        command(['cmake', '--build', str(build), '--parallel', '2'], area / 'build.log')
        run_env = dict(os.environ, LD_LIBRARY_PATH=str(root / LIB))
        for mode in ('shared', 'static'):
            executable = build / f'consumer-{mode}'
            command([str(executable)], area / f'run-{mode}.log', env=run_env)
            elf = command(['readelf', '-d', str(executable)], area / f'elf-{mode}.log').stdout
            expected = f'Shared library: [{soname}]'
            if (expected in elf) != (mode == 'shared'):
                raise RuntimeError(f'incorrect {mode} linkage for {package}')
        # Reproduce the original defective split: metadata survives but the
        # static archive is absent. Configure must fail on that exact import,
        # even though the shared consumer itself does not need a static archive.
        missing = root / LIB / archive
        saved = area / archive
        missing.rename(saved)
        try:
            failed = command(configure(area / 'negative-build'), area / 'negative.log', expected_failure=True)
            if str(missing) not in failed.stdout or static not in failed.stdout or 'does not exist' not in failed.stdout:
                raise RuntimeError(f'negative control failed for an unrelated reason: {failed.stdout}')
        finally:
            saved.rename(missing)
        record.update(shared_consumer='passed', static_consumer='passed',
                      missing_static_control='rejected exact missing imported archive')
        results.append(record)
        print(f'SDK closure passed: {package}; shared + static consumers; missing-static control', flush=True)
(WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
