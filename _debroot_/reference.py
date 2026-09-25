"""Coordinator-owned Debian root prerequisites Debian itself cannot supply.

Two sources, neither selectable by a recipe's paths:

* Rust toolchains, from Rust's own signed release archives, pinned here by
  hash. Peios already trusts these: its native Rust bootstraps from the same
  upstream binaries, which the rust recipe's build:vendor fetches as pinned by
  the source release's src/stage0. A Peios-built compiler cannot
  serve here, because the Debian rung is what builds the seed that a native
  compiler needs (PEI-1156).
* Catalogue packages a recipe names in its apt dependency set, such as
  dev.peios.libpeios-devel. They are composed from the signed Peios
  repository (verified against the pinned trust anchor), and only the files
  the named packages themselves own are copied into the Debian root; their
  Peios dependency closure (glibc and so on) never is. Because the apt set
  names a package another workspace member defines, pekit orders that member
  first even under the Debian env.
"""
import hashlib, json, os, re, shutil, stat, subprocess, tempfile, urllib.request
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent

RUST_KEY = HERE / 'keys' / 'rust-release.asc'
RUST_FINGERPRINT = '108F66205EAEB0AAA8DD5E1C85AB96E6FA1BE5FE'
RUST_DIST = 'https://static.rust-lang.org/dist/'
# Upstream release archives. The pins were taken after verifying each
# archive's detached signature by RUST_FINGERPRINT, which fetch() re-checks on
# every download; the hash is what binds a cached copy afterwards.
RUST_ARCHIVES = {
    'rust-1.98.1-x86_64-unknown-linux-gnu.tar.xz': '5326b36c53de11d148c8f8dab6553a3d1006c2cfd32123683073fad3c302605b',
    'rust-1.83.0-x86_64-unknown-linux-gnu.tar.xz': 'b6467a0e8a6c5dca35269785c994e4d80d89754d6c600162cc9146f90c87ee08',
    'rust-src-1.83.0.tar.xz': '1d6af46e3f944b2cb5cfaef7afb42e7ee00abb3285f3b09ca98bbcfff959c0c5',
}
TOOLCHAINS = {
    'rust-1.98.1': dict(version='1.98.1', archives=[
        ('rust-1.98.1-x86_64-unknown-linux-gnu.tar.xz',
         ['rustc', 'cargo', 'rust-std-x86_64-unknown-linux-gnu', 'rustfmt-preview'])]),
    # The kernel builds Rust-for-Linux with the toolchain pkm pins in
    # build/toolchain.lock. Kbuild compiles core from rust-src itself.
    'rust-1.83.0': dict(version='1.83.0', archives=[
        ('rust-1.83.0-x86_64-unknown-linux-gnu.tar.xz', ['rustc', 'rust-std-x86_64-unknown-linux-gnu', 'rustfmt-preview']),
        ('rust-src-1.83.0.tar.xz', ['rust-src'])]),
}

# Families whose Debian roots receive a pinned Rust toolchain in place of
# Debian's older one. Only minimal-bootstrap recipes build under Debian.
RUST_FAMILIES = {'dev.peios.resolvd', 'dev.peios.peiosutils'}
TARGETS = {'build-vendor', 'build-main', 'test-main'}
KERNEL_FAMILIES = {'dev.peios.kernel'}
# Every kernel target is reviewed here. Only the two that run rustc receive
# the toolchain; the rest keep plain Debian roots.
KERNEL_TOOLCHAIN_TARGETS = {'build-kunit', 'build-kernel'}
KERNEL_TARGETS = KERNEL_TOOLCHAIN_TARGETS | {
    'build-upstream', 'build-source', 'build-headers', 'build-debuginfo',
    'build-tools', 'build-fwsig', 'test-kunit', 'test-modsig', 'test-fwsig',
    'test-stratafs', 'test-uapi', 'gen-uapi',
    # Mount namespaces as KACS objects (PEI-1173): the same QEMU initramfs
    # smoke shape as test-stratafs, with the same apt set.
    'test-mntns',
    # The Rust cores' cargo suites use Debian's own rustc/cargo (1.85 meets
    # the workspace's rust-version), not the pinned kernel toolchain.
    'test-cores',
}
# Debian packages a toolchain replaces. A recipe may only name them
# unconstrained: the pin, not the recipe, chooses the version.
TOOLCHAIN_REPLACES = ['cargo', 'rustc', 'rustfmt']
# What the overlay and its runtime preflight need from Debian.
RUNTIME_APT = ['binutils', 'gcc', 'libc6-dev', 'python3', 'pkgconf']
# Catalogue packages whose files would collide with Debian's own: take only
# the Peios-specific subtree. The Linux UAPI headers come from linux-libc-dev.
CATALOGUE_SUBTREES = {'dev.peios.kernel-headers': ['usr/include/pkm']}
# Reverse-DNS catalogue names. Such a name missing from the repository is an
# error rather than an apt request that would fail obscurely.
CATALOGUE_NAME = re.compile(r'(com|org|net|io|dev|se|cz)\.[a-z0-9-]+\.[a-z0-9.+-]+')
LIBDIR = 'usr/lib/x86_64-linux-peios'


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n').encode()


def policy_digest():
    """Everything in this module that decides a root's contents."""
    return hashlib.sha256(encoded(dict(archives=RUST_ARCHIVES, toolchains=TOOLCHAINS,
                                       subtrees=CATALOGUE_SUBTREES))).hexdigest()


# ---- selection ---------------------------------------------------------------

def toolchain_for(family, target):
    if family in KERNEL_FAMILIES:
        if target not in KERNEL_TARGETS:
            raise ValueError('reference family has an unreviewed target: ' + target)
        return 'rust-1.83.0' if target in KERNEL_TOOLCHAIN_TARGETS else None
    if family in RUST_FAMILIES:
        if target not in TARGETS:
            raise ValueError('reference family has an unreviewed target: ' + target)
        return 'rust-1.98.1'
    return None


def is_catalogue_name(name):
    return CATALOGUE_NAME.fullmatch(name) is not None


def split_catalogue(deps, index_names):
    """Separate catalogue requests from apt ones. Only a reverse-DNS name is a
    catalogue request: the repository still carries unqualified historical
    packages whose names (debugedit, say) are also Debian's."""
    catalogue, apt = [], []
    for dep in deps:
        if not is_catalogue_name(dep['name']):
            apt.append(dep)
        elif dep['name'] in index_names:
            catalogue.append(dep)
        else:
            raise ValueError('catalogue package is not in the repository: ' + dep['name'])
    return catalogue, apt


def selection(family, target, deps, index_names):
    toolchain = toolchain_for(family, target)
    catalogue, _ = split_catalogue(deps, index_names)
    if toolchain is None and not catalogue:
        return None
    return dict(schema=2, family=family, target=target, toolchain=toolchain,
                catalogue=catalogue, policy_sha256=policy_digest())


def effective_requests(original, selected, index_names):
    if selected is None:
        return original
    _, apt = split_catalogue(original, index_names)
    result = []
    for dep in apt:
        if selected['toolchain'] and dep['name'] in TOOLCHAIN_REPLACES:
            if dep['checks']:
                raise ValueError('non-wildcard reference substitution: ' + dep['name'])
            continue
        result.append(dep)
    existing = {d['name'] for d in result}
    for name in RUNTIME_APT:
        if name not in existing:
            result.append(dict(name=name, checks=[]))
    return sorted(result, key=lambda d: d['name'])


# ---- paths -------------------------------------------------------------------

def relative(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or str(p) != name.rstrip('/'):
        raise ValueError('unsafe path: ' + name)
    if p.parts[0] != 'usr':
        raise ValueError('reference payload outside /usr: ' + name)
    return p


def parent_safe(root, path):
    rel = path.relative_to(root)
    p = root
    for component in rel.parts[:-1]:
        p = p / component
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise ValueError('symlink/non-directory parent: ' + str(p))
        p.mkdir(exist_ok=True)


def place(root, source, name):
    """Copy one entry from a composed or staged tree into the overlay root."""
    rel = relative(name)
    dest = root / str(rel)
    parent_safe(root, dest)
    info = source.lstat()
    if stat.S_ISDIR(info.st_mode):
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            raise ValueError('directory collision: ' + name)
        dest.mkdir(exist_ok=True)
        return
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)) or info.st_mode & 0o7000:
        raise ValueError('unsupported file type/mode: ' + name)
    if dest.exists() or dest.is_symlink():
        raise ValueError('reference payload collision: ' + name)
    if stat.S_ISLNK(info.st_mode):
        target = PurePosixPath(os.readlink(source))
        if target.is_absolute():
            raise ValueError('absolute reference symlink: ' + name)
        normalized = PurePosixPath(os.path.normpath(str(rel.parent / target)))
        if normalized.parts[0] != 'usr' or '..' in normalized.parts:
            raise ValueError('escaping reference symlink: ' + name)
        dest.symlink_to(target)
        return
    shutil.copyfile(source, dest)
    dest.chmod(stat.S_IMODE(info.st_mode))


# ---- Rust toolchains ---------------------------------------------------------

def fetch(name, cache):
    """A pinned upstream archive, downloaded once and signature-checked."""
    pin = RUST_ARCHIVES[name]
    path = cache / name
    if path.exists():
        if digest(path) != pin:
            raise ValueError('cached upstream archive changed: ' + name)
        return path
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.fetch-', dir=cache) as temp:
        temp = Path(temp)
        archive, signature = temp / name, temp / (name + '.asc')
        for url, dest in [(RUST_DIST + name, archive), (RUST_DIST + name + '.asc', signature)]:
            with urllib.request.urlopen(url, timeout=120) as response, dest.open('wb') as out:
                shutil.copyfileobj(response, out)
        if digest(archive) != pin:
            raise ValueError('upstream archive does not match its pin: ' + name)
        keyring = temp / 'rust-release.gpg'
        subprocess.run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(keyring), str(RUST_KEY)],
                       check=True, capture_output=True)
        status = subprocess.run(['gpgv', '--status-fd', '1', '--keyring', str(keyring), str(signature), str(archive)],
                                capture_output=True, text=True)
        if f'[GNUPG:] VALIDSIG {RUST_FINGERPRINT} ' not in status.stdout:
            raise ValueError('upstream archive signature not valid for the Rust release key: ' + name)
        os.replace(archive, path)
    return path


def install_toolchain(name, stage, cache):
    """Run upstream's installer for the pinned components into stage/usr."""
    prefix = stage / 'usr'
    for archive, components in TOOLCHAINS[name]['archives']:
        path = fetch(archive, cache)
        with tempfile.TemporaryDirectory(prefix='.unpack-') as unpack:
            subprocess.run(['tar', '-xJf', str(path), '-C', unpack], check=True)
            installers = list(Path(unpack).glob('*/install.sh'))
            if len(installers) != 1:
                raise ValueError('unexpected upstream archive layout: ' + archive)
            subprocess.run(['bash', str(installers[0]), '--prefix=' + str(prefix), '--disable-ldconfig',
                            '--components=' + ','.join(components)],
                           check=True, capture_output=True)
    # The installer records the staging path it ran with. Name the path the
    # files will actually have, and drop its host-specific log.
    rustlib = prefix / 'lib' / 'rustlib'
    (rustlib / 'install.log').unlink(missing_ok=True)
    for meta in rustlib.iterdir():
        if meta.is_file() and not meta.is_symlink():
            data = meta.read_bytes()
            if str(stage).encode() in data:
                meta.write_bytes(data.replace(str(stage).encode(), b''))
    return dict(name=name, version=TOOLCHAINS[name]['version'],
                archives={a: RUST_ARCHIVES[a] for a, _ in TOOLCHAINS[name]['archives']})


# ---- catalogue packages ------------------------------------------------------

def repository():
    """This job's frozen repository snapshot and its pinned trust anchor."""
    snapshot = subprocess.run([shutil.which('python3') or 'python3',
                               str(WORKSPACE / '_peiroot_' / 'snapshot-repository.py')],
                              check=True, capture_output=True, text=True).stdout.strip()
    anchor = (WORKSPACE / '_peiroot_' / 'repository.anchor').read_text().strip()
    if not re.fullmatch('[a-f0-9]{64}', anchor):
        raise ValueError('invalid repository trust anchor')
    return Path(snapshot), anchor


def index_names(snapshot):
    return {p['name'] for p in json.loads((snapshot / 'index' / 'active.json').read_text())['packages']}


def constraint(checks):
    return ', '.join(f'{op} {version}' for op, version in checks) or '*'


def install_catalogue(catalogue, stage, snapshot, anchor, work):
    """Compose the named packages from the signed repository into a scratch
    root, then copy only the files each named package owns."""
    manifest = work / 'root.toml'
    lines = ['schema = 1', 'arch = "x86_64"', 'source_date = "2026-01-01T00:00:00Z"',
             '[[repository]]', 'name = "peios"', f'base_url = "file://{snapshot}"',
             'priority = 10', 'signature_policy = "required"', f'trust_anchors = ["{anchor}"]']
    for dep in catalogue:
        lines += ['[[package]]', f'name = "{dep["name"]}"', f'version = "{constraint(dep["checks"])}"']
    manifest.write_text('\n'.join(lines) + '\n')
    scratch = work / 'scratch'
    # --no-dependencies: only the named packages' own files are taken below,
    # and what they need at run time comes from the Debian set. Resolving
    # their catalogue closure would make a seed build wait for packages the
    # seed cannot have yet (packaging-tools needs python3, bindgen clang).
    subprocess.run(['peipkg-compose', 'build', str(manifest), '--out', str(scratch),
                    '--record-xattrs', str(work / 'xattrs.jsonl'), '--dangerously-bypass-path-restrictions',
                    '--no-dependencies'],
                   check=True, capture_output=True)
    installed = {}
    for line in subprocess.run(['peipkg', '--root', str(scratch), 'list'], check=True,
                               capture_output=True, text=True).stdout.splitlines():
        name, version, *_ = line.split()
        installed[name] = version
    record = []
    for dep in catalogue:
        name = dep['name']
        owned = subprocess.run(['peipkg', '--root', str(scratch), 'files', name], check=True,
                               capture_output=True, text=True).stdout.splitlines()
        keep = CATALOGUE_SUBTREES.get(name)
        copied = 0
        for path in owned:
            rel = path.lstrip('/')
            if not rel or rel == 'usr':
                continue
            if keep and not any(rel == k or rel.startswith(k + '/') or k.startswith(rel + '/') for k in keep):
                continue
            place(stage, scratch / rel, rel)
            copied += 1
        if not copied:
            raise ValueError('catalogue package contributed no files: ' + name)
        record.append(dict(name=name, version=installed[name], subtrees=keep))
    lock = work / 'root.lock.toml'
    return dict(packages=record, lock_sha256=digest(lock) if lock.exists() else None)


# ---- overlay -----------------------------------------------------------------

def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            result[rel] = {'link': os.readlink(p)}
        elif p.is_file():
            result[rel] = {'sha256': digest(p), 'mode': stat.S_IMODE(p.stat().st_mode)}
        elif p.is_dir():
            result[rel] = {'directory': True}
        else:
            raise ValueError('special reference file')
    return result


def build_overlay(selected, directory, cache):
    directory.mkdir(exist_ok=False)
    stage = directory / 'root'
    stage.mkdir()
    toolchain = catalogue = None
    if selected['toolchain']:
        toolchain = install_toolchain(selected['toolchain'], stage, cache)
    if selected['catalogue']:
        snapshot, anchor = repository()
        work = directory / 'catalogue'
        work.mkdir()
        catalogue = install_catalogue(selected['catalogue'], stage, snapshot, anchor, work)
        shutil.rmtree(work / 'scratch')
        libroot = stage / LIBDIR / 'pkgconfig'
        for pc in sorted(libroot.glob('*.pc')):
            dest = stage / 'usr/lib/pkgconfig' / pc.name
            parent_safe(stage, dest)
            if dest.exists() or dest.is_symlink():
                raise ValueError('pkgconfig compatibility collision')
            dest.symlink_to('../x86_64-linux-peios/pkgconfig/' + pc.name)
    record = dict(schema=2, selection=selected, toolchain=toolchain, catalogue=catalogue,
                  payload=inventory(stage), adapter_sha256=digest(__file__))
    (directory / 'reference-prerequisites.json').write_bytes(encoded(record))
    return record


# Runs inside the Debian container against the exact overlay inventory before
# any copy. Existing ordinary directories may merge; no file or symlink
# replacement is authorized.
COLLISION_CHECK = r'''
import json,os,stat,sys
from pathlib import Path
inventory=json.load(sys.stdin)
for name,entry in inventory.items():
 p=Path('/')/name; current=Path('/')
 for part in Path(name).parts[:-1]:
  current=current/part
  if current.is_symlink():raise SystemExit('symlink parent collision: '+name)
 if p.exists() or p.is_symlink():
  if entry.get('directory') and p.is_dir() and not p.is_symlink():continue
  raise SystemExit('APT/reference collision: '+name)
if Path('/etc/ld.so.conf.d/pekit-reference.conf').exists():raise SystemExit('reference ldconfig collision')
'''

# Runs only inside the new disposable Debian coordinator container. It verifies
# actual loader resolution and hashes every selected transitive DSO; no worker
# compilation or acquisition is delegated to the host.
RUNTIME_CHECK = r'''
import hashlib,json,re,shlex,subprocess,sys,tempfile
from pathlib import Path
record=json.load(sys.stdin);root=Path('/');checks=[];runtime={}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(cmd):
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
 checks.append(dict(command=cmd,status=p.returncode,output=p.stdout))
 if p.returncode:raise SystemExit(json.dumps(checks))
 return p.stdout
for name,entry in record['payload'].items():
 p=root/name
 if entry.get('sha256'):
  if sha(p)!=entry['sha256']:raise SystemExit('copied bytes changed: '+name)
  with p.open('rb') as f:elf=f.read(4)==b'\x7fELF'
  if not elf:continue
  dynamic=run(['/usr/bin/readelf','-dW',str(p)])
  if '(NEEDED)' not in dynamic:continue
  output=run(['/usr/bin/ldd',str(p)])
  if 'not found' in output:raise SystemExit('unresolved library: '+name)
  for line in output.splitlines():
   match=re.search(r'(?:=>\s+)?(/\S+)\s+\(',line)
   if match:
    dep=Path(match[1]).resolve(strict=True);runtime[str(dep)]=sha(dep)
 elif entry.get('link') is not None:
  if not p.is_symlink() or str(p.readlink())!=entry['link']:raise SystemExit('copied link changed: '+name)
probe='fn main() { let x=std::thread::spawn(|| vec![1u32,2,3].iter().sum::<u32>()); assert_eq!(x.join().unwrap(),6); }\n'
toolchain=record.get('toolchain')
if toolchain:
 expected=toolchain['version']
 tools=['rustc','rustdoc']+(['cargo'] if toolchain['name'].startswith('rust-1.98') else [])
 for name in tools:
  if run(['/usr/bin/'+name,'--version']).split()[:2]!=[name,expected]:raise SystemExit('wrong reference tool: '+name)
 run(['/usr/bin/rustfmt','--version'])
 with tempfile.TemporaryDirectory(prefix='reference-consumer-') as td:
  td=Path(td);src=td/'main.rs';exe=td/'main'
  src.write_text(probe)
  run(['/usr/bin/rustc',str(src),'-o',str(exe)]);run([str(exe)])
 # Kbuild compiles core from the toolchain's own rust-src (RUST_LIB_SRC).
 if toolchain['name']=='rust-1.83.0' and not Path('/usr/lib/rustlib/src/rust/library/core/src/lib.rs').is_file():
  raise SystemExit('reference rust-src missing')
catalogue={p['name']:p['version'] for p in (record.get('catalogue') or {}).get('packages',[])}
if 'io.github.rust-lang.bindgen' in catalogue:
 expected=catalogue['io.github.rust-lang.bindgen'].rsplit('-',1)[0]
 if run(['/usr/bin/bindgen','--version']).split()[:2]!=['bindgen',expected]:
  raise SystemExit('wrong reference tool: bindgen')
 # bindgen loads libclang at run time instead of linking it, so the readelf/ldd
 # pass above cannot see that dependency. Generating a binding proves it.
 with tempfile.TemporaryDirectory(prefix='reference-bindgen-') as td:
  header=Path(td)/'probe.h';header.write_text('struct pekit_reference_probe { int value; };\n')
  if 'pekit_reference_probe' not in run(['/usr/bin/bindgen',str(header)]):
   raise SystemExit('bindgen produced no binding')
for library,pc,header in [('dev.peios.libpeios-devel','peios','peios.h'),('dev.peios.librsi-devel','rsi','rsi.h')]:
 if library not in catalogue:continue
 if run(['/usr/bin/pkg-config','--modversion',pc]).strip()!=catalogue[library].rsplit('-',1)[0]:raise SystemExit('wrong SDK version')
 flags=shlex.split(run(['/usr/bin/pkg-config','--cflags','--libs',pc]))
 with tempfile.TemporaryDirectory(prefix='reference-abi-') as td:
  td=Path(td);src=td/'main.c';exe=td/'main'
  src.write_text('#include <'+header+'>\nint main(void) { return 0; }\n')
  run(['/usr/bin/gcc',str(src),'-Wl,--no-as-needed',*flags,'-o',str(exe)]);run([str(exe)])
print(json.dumps(dict(passed=True,checks=checks,resolved_runtime_sha256=runtime),sort_keys=True))
'''


def install_container(container, selected, directory, cache):
    record = build_overlay(selected, directory, cache)
    subprocess.run(['docker', 'exec', '-i', container, 'python3', '-c', COLLISION_CHECK],
                   input=encoded(record['payload']), check=True)
    subprocess.run(['docker', 'cp', str(directory / 'root/usr') + '/.', container + ':/usr/'], check=True)
    if any(name.startswith(LIBDIR + '/') for name in record['payload']):
        # Generated coordinator policy, not a payload permitted to overwrite
        # arbitrary configuration. The collision guard checked it first.
        subprocess.run(['docker', 'exec', '-i', container, 'python3', '-c',
                        "from pathlib import Path; import sys; p=Path('/etc/ld.so.conf.d/pekit-reference.conf'); "
                        "p.parent.mkdir(parents=True,exist_ok=True); p.open('xb').write(sys.stdin.buffer.read())"],
                       input=('/' + LIBDIR + '\n').encode(), check=True)
    subprocess.run(['docker', 'exec', container, '/sbin/ldconfig'], check=True)
    result = subprocess.run(['docker', 'exec', '-i', container, 'python3', '-c', RUNTIME_CHECK],
                            input=encoded(record), capture_output=True)
    if result.returncode:
        # The check exits with its transcript; the last command is the failure.
        detail = result.stderr.decode(errors='replace').strip()
        try:
            failed = json.loads(detail)[-1]
            detail = f"{' '.join(failed['command'])} -> {failed['status']}: {failed['output'].strip()[-2000:]}"
        except (ValueError, KeyError, IndexError, TypeError):
            detail = detail[-2000:]
        raise ValueError('reference runtime check failed: ' + detail)
    check = json.loads(result.stdout)
    if check.get('passed') is not True:
        raise ValueError('reference runtime not validated')
    record['runtime'] = check
    evidence = encoded(record)
    subprocess.run(['docker', 'exec', '-i', container, 'python3', '-c',
                    "from pathlib import Path; import sys; p=Path('/usr/share/pekit-reference/reference-prerequisites.json'); "
                    "p.parent.mkdir(parents=True,exist_ok=True); p.open('xb').write(sys.stdin.buffer.read())"],
                   input=evidence, check=True)
    (directory / 'reference-prerequisites.json').write_bytes(evidence)
    return record
