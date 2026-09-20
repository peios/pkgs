#!/usr/bin/env python3
"""Bounded installed-toolchain regressions, not the complete compiletest suite."""
import argparse, hashlib, json, os
from pathlib import Path
import subprocess

UPSTREAM = [
    'threads-sendsync/task-comm-14.rs',
    'threads-sendsync/tls-try-with.rs',
    'functions-closures/nullable-pointer-opt-closures.rs',
    'consts/const-int-overflowing-rpass.rs',
    'simd/size-align.rs',
    'intrinsics/intrinsic-volatile.rs',
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--targets', nargs='+', required=True)
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parent
    env = dict(os.environ, RUSTC_BOOTSTRAP='1')
    events = []
    result = {'scope': __doc__, 'targets': args.targets, 'upstream': [], 'commands': events}
    evidence = args.out / 'regression-results.json'
    def run(argv, label, cwd=None):
        completed = subprocess.run([str(a) for a in argv], cwd=cwd or args.out,
                                   env=env, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=180)
        events.append({'label': label, 'argv': [str(a) for a in argv],
                       'exit_code': completed.returncode, 'output': completed.stdout})
        evidence.write_text(json.dumps(result, indent=2) + '\n')
        if completed.returncode:
            raise RuntimeError(f'{label}: {completed.stdout}')
        print('PASS', label, flush=True)
        return completed.stdout
    result['rustc'] = run(['rustc', '--version', '--verbose'], 'compiler identity')
    result['rustdoc'] = run(['rustdoc', '--version'], 'rustdoc identity')
    native = 'x86_64-unknown-linux-gnu'
    allowed = {native, 'x86_64-unknown-linux-musl'}
    if len(set(args.targets)) != len(args.targets) or not set(args.targets) <= allowed:
        raise ValueError('unsupported or duplicate target')
    upstream = []
    for name in UPSTREAM:
        source = args.source / 'tests/ui' / name
        text = source.read_text()
        directives = [line.strip()[3:].strip() for line in text.splitlines()
                      if line.strip().startswith('//@')]
        if 'run-pass' not in directives or any(d not in ('run-pass', 'needs-threads') for d in directives):
            raise ValueError(f'unsupported compiletest directives in {name}: {directives}')
        if '//~' in text:
            raise ValueError(f'unexpected diagnostic expectations in {name}')
        result['upstream'].append({'id': 'tests/ui/' + name,
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'directives': directives})
        upstream.append(source)
    def flags(target, optimization, edition=True):
        options = (['--edition=2021'] if edition else []) + ['--target', target, '-C', f'opt-level={optimization}',
                   '-C', 'linker=cc', '-Zcf-protection=full', '-C', 'link-arg=-Wl,-z,ibtplt']
        if target.endswith('-musl'):
            options += ['-C', 'relocation-model=pic', '-C', 'link-self-contained=yes',
                        '-C', 'link-arg=-static-pie']
        return options
    upstream_runs = 0
    for target in args.targets:
        for opt in (0, 2):
            for number, source in enumerate(upstream):
                output = args.out / f'upstream-{number}-{target}-O{opt}'
                label = f'{result["upstream"][number]["id"]} {target} O{opt}'
                run(['rustc', source, '--crate-name', f'upstream_regression_{number}',
                     *flags(target, opt, edition=False), '-o', output], label + ' compile')
                run([output], label + ' execute')
                upstream_runs += 1
    # This C object intentionally uses no libc facilities: its calling convention
    # and repr(C) aggregate/callback contract are shared by both x86_64 targets.
    run(['cc', '-O2', '-fPIC', '-fcf-protection=full', '-c', fixtures/'ffi.c',
         '-o', args.out/'ffi.o'], 'C ABI object compile')
    run(['ar', 'rcs', args.out/'libpeios_regression_ffi.a', args.out/'ffi.o'], 'C ABI archive')
    fixture_runs = 0
    for target in args.targets:
        for opt in (0, 2):
            for name in ('runtime', 'ffi'):
                output = args.out / f'{name}-{target}-O{opt}'
                extra = ['-L', f'native={args.out}', '-l', 'static=peios_regression_ffi'] if name == 'ffi' else []
                # ThinLTO adds a real optimizer/link pipeline exercise at O2.
                if name == 'runtime' and opt == 2:
                    extra += ['-C', 'lto=thin', '-C', 'codegen-units=2']
                label = f'{name} {target} O{opt}'
                run(['rustc', fixtures/(name+'.rs'), *flags(target,opt), *extra, '-o', output], label+' compile')
                run([output], label+' execute')
                fixture_runs += 1
    macro = args.out/'libpeios_regression_macro.so'
    run(['rustc', fixtures/'macro.rs', '--crate-name', 'peios_regression_macro',
         '--crate-type', 'proc-macro', *flags(native,2), '-o', macro], 'host proc-macro compile')
    for target in args.targets:
        output = args.out / ('macro-consumer-' + target)
        run(['rustc', fixtures/'macro-consumer.rs', '--crate-name', 'macro_consumer',
             *flags(target,2), '--extern', 'peios_regression_macro='+str(macro), '-o', output],
            'proc-macro consumer '+target+' compile')
        run([output], 'proc-macro consumer '+target+' execute')
    doctests = run(['rustdoc', '--edition=2021', '--test', fixtures/'docs.rs', '--test-args', '--nocapture'], 'rustdoc three doctests')
    if '3 passed; 0 failed; 0 ignored' not in doctests:
        raise RuntimeError('rustdoc did not execute all three positive/negative doctests')
    html = args.out/'html'
    run(['rustdoc', '--edition=2021', '--crate-name', 'regression_docs', fixtures/'docs.rs', '-o', html], 'rustdoc HTML generation')
    page = html/'regression_docs/fn.documented_value.html'
    if not page.is_file() or 'documented_value' not in page.read_text():
        raise RuntimeError('rustdoc HTML output is missing its documented API')
    result.update(passed=True, upstream_execute_count=upstream_runs,
                  runtime_ffi_execute_count=fixture_runs,
                  proc_macro_consumer_execute_count=len(args.targets), doctests_passed=3,
                  doctests_ignored=0, html_api_checked=True, filecheck_comparisons=0)
    evidence.write_text(json.dumps(result,indent=2)+'\n')
    print('RUST_REGRESSION_SUMMARY ' + json.dumps({k:v for k,v in result.items() if k != 'commands'}, sort_keys=True), flush=True)
    print('All bounded installed-toolchain regressions passed', flush=True)

if __name__ == '__main__':
    main()
