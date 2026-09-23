#!/bin/python3
"""Mandatory generic counting regressions, with an optional validated LSan check."""
import argparse, hashlib, json, os, re, signal, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--clang', required=True, type=Path)
p.add_argument('--fixtures', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
p.add_argument('--leak-runtime', type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
sha = lambda f: hashlib.file_digest(Path(f).open('rb'), 'sha256').hexdigest()
env = dict(os.environ)
for name in ['CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
             'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'CFLAGS', 'CXXFLAGS',
             'CPPFLAGS', 'LDFLAGS', 'LD_PRELOAD', 'LSAN_OPTIONS', 'ASAN_OPTIONS']:
    env.pop(name, None)
rows = []
def run(label, command, extra=None):
    local = dict(env)
    if extra:
        local.update(extra)
    child = subprocess.Popen([str(x) for x in command], env=local,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
    try:
        stdout, stderr = child.communicate(timeout=120)
        code, text = child.returncode, stdout + stderr
    except subprocess.TimeoutExpired:
        # The driver can own cc1/linker children; kill and reap the whole group.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = child.communicate()
        code, text = 124, stdout + stderr + '\nTIMEOUT after 120 seconds\n'
    log = a.output / (label + '.log')
    log.write_text(text)
    row = {'label': label, 'command': [str(x) for x in command], 'returncode': code,
           'log_sha256': sha(log), 'environment_additions': extra or {}}
    rows.append(row)
    return row, text
positive = a.fixtures / 'peios-generic-counting.cpp'
negative = a.fixtures / 'peios-generic-counting-invalid.cpp'
expected_names = {f'invalid_{op}_{i}' for op in ['clz', 'ctz'] for i in range(4)}
crash = re.compile(r'PLEASE submit a bug report|Assertion .*failed|LLVM ERROR|AddressSanitizer|LeakSanitizer|Segmentation fault|Stack dump:')
def check_negative(label, extra=None):
    row, text = run(label, [a.clang, '-cc1', '-std=c++17', '-ferror-limit', '0',
                           '-fexperimental-new-constant-interpreter', '-fsyntax-only', negative], extra)
    names = set(re.findall(r"error: constexpr variable '(invalid_\w+)' must be initialized by a constant expression", text))
    row['passed'] = row['returncode'] == 1 and names == expected_names and len(re.findall(r'error:', text)) == 8 and not crash.search(text)
    row['diagnosed_names'] = sorted(names)
    return row
for mode, flags in [('default', []), ('experimental', ['-fexperimental-new-constant-interpreter'])]:
    row, text = run(mode + '-positive', [a.clang, '-cc1', '-std=c++17', *flags, '-fsyntax-only', positive])
    row['passed'] = row['returncode'] == 0 and not crash.search(text)
    row, text = run(mode + '-negative', [a.clang, '-cc1', '-std=c++17', '-ferror-limit', '0', *flags, '-fsyntax-only', negative])
    names = set(re.findall(r"error: constexpr variable '(invalid_\w+)' must be initialized by a constant expression", text))
    row['passed'] = row['returncode'] == 1 and names == expected_names and len(re.findall(r'error:', text)) == 8 and not crash.search(text)
    row['diagnosed_names'] = sorted(names)
for level in ['0', '2']:
    exe = a.output / ('counting-O' + level)
    row, text = run('compile-O' + level, [a.clang, '-x', 'c++', '-std=c++17', '-O' + level, positive, '-o', exe])
    row['passed'] = row['returncode'] == 0 and not crash.search(text)
    if row['passed']:
        row, text = run('runtime-O' + level, [exe])
        row['passed'] = row['returncode'] == 0 and not text
leak = {'requested': bool(a.leak_runtime), 'validated': False}
if a.leak_runtime:
    # Standalone runtime, loaded into the real compiler. A deliberate leak must
    # actually be detected in this namespace before clean results mean anything.
    leak.update(runtime=str(a.leak_runtime), sha256=sha(a.leak_runtime))
    options = {'LD_PRELOAD': str(a.leak_runtime),
               'LSAN_OPTIONS': 'detect_leaks=1:exitcode=23:report_objects=1:symbolize=0'}
    for name, body in [('clean', 'void *p = malloc(123); free(p);'),
                       ('leaking', 'void * volatile p = malloc(123); p = 0;')]:
        src = a.output / (name + '.c')
        src.write_text('#include <stdlib.h>\n__attribute__((noinline)) void probe(void) { ' + body + ' }\nint main(void) { probe(); return 0; }\n')
        exe = a.output / name
        row, text = run(name + '-compile', [a.clang, '-O0', src, '-o', exe])
        row['passed'] = row['returncode'] == 0
        if row['passed']:
            row, text = run(name + '-lsan-control', [exe], options)
            row['passed'] = (row['returncode'] == 0 and not text) if name == 'clean' else (row['returncode'] == 23 and 'LeakSanitizer: detected memory leaks' in text and '123 byte(s) leaked' in text)
    controls = [r for r in rows if r['label'].endswith('-lsan-control')]
    leak['validated'] = len(controls) == 2 and all(r['passed'] for r in controls)
    if leak['validated']:
        row, text = run('positive-lsan', [a.clang, '-cc1', '-std=c++17', '-fexperimental-new-constant-interpreter', '-fsyntax-only', positive], options)
        row['passed'] = row['returncode'] == 0 and not crash.search(text)
        check_negative('negative-lsan', options)
    else:
        leak['limitation'] = 'Leak detector controls failed; no memory-safety inference from compiler exit status.'
passed = all(r.get('passed', False) for r in rows) and (not a.leak_runtime or leak['validated'])
report = {'compiler': str(a.clang), 'compiler_sha256': sha(a.clang.resolve()),
          'fixtures': {str(f): sha(f) for f in [positive, negative]},
          'results': rows, 'leak_check': leak, 'passed': passed}
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': passed, 'cases': len(rows), 'leak_detector_validated': leak['validated']}))
raise SystemExit(0 if passed else 1)
