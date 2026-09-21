"""Coordinator-owned signed reference SDK; never accepts recipe-supplied paths."""
import functools, hashlib, json, os, pwd, re, shutil, stat, subprocess, tarfile, tempfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
# Fixed operator-owned service configuration, never selected by recipe env.
CONFIG = Path(pwd.getpwuid(os.getuid()).pw_dir) / '.local/state/pekit/reference/selection.json'
SDK_FAMILIES = {
    'dev.peios.authd', 'dev.peios.eventd', 'dev.peios.timed', 'dev.peios.resolvd',
    'dev.peios.trustd', 'dev.peios.atrium', 'dev.peios.netd', 'dev.peios.pnpd',
    'dev.peios.peiosutils',
}
MUSL_FAMILIES = {'dev.peios.peios-installer'}
RUST_FAMILIES = SDK_FAMILIES | MUSL_FAMILIES
SID_FAMILIES = RUST_FAMILIES | {'dev.peios.loregd', 'dev.peios.peipkg'}
TARGETS = {'build-vendor', 'build-main', 'test-main'}
# The kernel builds Rust-for-Linux against the toolchain pkm pins in
# build/toolchain.lock — rustc 1.83.0 and bindgen 0.65.1 — which Debian cannot
# supply. It receives those two qualified families and nothing else, on its
# ordinary trixie base: both were qualified on trixie, and this rustc links
# trixie's libLLVM-18, so the kernel is deliberately not a SID family.
KERNEL_FAMILIES = {'dev.peios.kernel'}
# Every kernel target is reviewed here. Only the two that run rustc and bindgen
# receive the toolchain; the rest keep plain Debian roots.
KERNEL_TOOLCHAIN_TARGETS = {'build-kunit', 'build-kernel'}
KERNEL_TARGETS = KERNEL_TOOLCHAIN_TARGETS | {
    'build-upstream', 'build-source', 'build-headers', 'build-debuginfo',
    'build-tools', 'build-fwsig', 'test-kunit', 'test-modsig', 'test-fwsig',
    'test-stratafs', 'test-uapi', 'gen-uapi',
}
# Families whose Debian roots may receive a coordinator-selected overlay.
OVERLAY_FAMILIES = RUST_FAMILIES | KERNEL_FAMILIES
# Debian runtime the 1.98 SDK overlay and its preflight need (libLLVM-23 for
# rustc; OpenSSL, zstd and zlib for cargo).
SDK_RUNTIME_APT = ['libllvm23', 'libstdc++6', 'libgcc-s1', 'libssl3t64', 'libzstd1', 'zlib1g',
                   'python3', 'binutils', 'gcc', 'libc6-dev', 'pkgconf', 'ca-certificates']
# The kernel toolchain's: libLLVM-18 for rustc, and what the preflight uses to
# inspect and link. No cargo, so none of its libraries.
KERNEL_RUNTIME_APT = ['libllvm18', 'libstdc++6', 'libgcc-s1',
                      'python3', 'binutils', 'gcc', 'libc6-dev']

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def encoded(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n').encode()

_job_configuration = None

@functools.lru_cache(maxsize=1)
def configuration():
    if _job_configuration is not None:
        return _job_configuration
    directory = CONFIG.parent.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077:
        raise ValueError('reference operator directory must be owned by coordinator uid, mode0700')
    with os.fdopen(os.open(CONFIG, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('reference operator selection must be a private regular file owned by coordinator uid')
        config = json.load(stream)
    if config.get('schema') != 1:
        raise ValueError('unsupported reference policy schema')
    return config

def bind_job_configuration(job, family):
    """Called by prepare under job/debian.lock, before policy or selection reads.

    Normal Pekit jobs have private coordinator-owned directories. Capture once
    before the first reference root; later targets use the same bytes even if
    a newer qualified SDK becomes the operator default in the meantime.
    """
    global _job_configuration
    _job_configuration = None
    configuration.cache_clear()
    if family not in OVERLAY_FAMILIES:
        return
    destination = Path(job) / 'dependencies' / 'reference-selection.json'
    if destination.exists() or destination.is_symlink():
        with os.fdopen(os.open(destination, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError('unsafe captured reference selection')
            record = json.load(f)
    else:
        config = configuration()
        record = dict(schema=1, family=family, configuration=config,
                      configuration_sha256=hashlib.sha256(encoded(config)).hexdigest())
        destination.parent.mkdir(exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.reference-selection-', dir=destination.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(encoded(record)); f.flush(); os.fsync(f.fileno())
            os.link(temporary, destination, follow_symlinks=False)
            fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            Path(temporary).unlink()
    config = record.get('configuration')
    if (record.get('schema') != 1 or record.get('family') != family
            or not isinstance(config, dict) or config.get('schema') != 1
            or hashlib.sha256(encoded(config)).hexdigest() != record.get('configuration_sha256')):
        raise ValueError('corrupt captured reference selection')
    # Fail closed on a mixed historical job rather than changing its policy and
    # silently acquiring new roots beside outputs produced with the old SDK.
    for path in destination.parent.glob('*/debian-root.json'):
        prior = json.loads(path.read_text()).get('reference_selection')
        if prior and prior.get('operator_configuration_sha256') != record['configuration_sha256']:
            raise ValueError('reference selection differs from existing job roots')
    _job_configuration = config
    configuration.cache_clear()

def configuration_digest():
    return hashlib.sha256(encoded(configuration())).hexdigest()

def selection(family, target):
    if family in KERNEL_FAMILIES:
        if target not in KERNEL_TARGETS:
            raise ValueError('reference family has an unreviewed target: ' + target)
        if target not in KERNEL_TOOLCHAIN_TARGETS:
            return None
        # Operator policy, not recipe-controlled substitution.
        return _selected(family, target, ['rust-1.83', 'bindgen'], 'debian:trixie',
                         ['bindgen', 'cargo', 'rustc', 'rustfmt'])
    if family not in SID_FAMILIES:
        return None
    if target not in TARGETS:
        raise ValueError('reference family has an unreviewed target: ' + target)
    groups = []
    if family in RUST_FAMILIES:
        groups.append('rust')
        if target != 'build-vendor':
            # Operator policy, not recipe-controlled substitution.
            if family in SDK_FAMILIES:
                groups.append('libpeios-current')
            if family in MUSL_FAMILIES:
                groups.append('rust-musl')
    return _selected(family, target, groups, 'debian:sid', ['cargo', 'rustc'] if groups else [])

def _selected(family, target, groups, image, replace_apt):
    config = configuration() if groups else None
    selected = []
    for key in groups:
        group = config['groups'].get(key)
        if group is None:
            raise ValueError('reference prerequisite not qualified/selected: ' + key)
        selected.append(group)
    return dict(schema=1, family=family, target=target, image=image, groups=selected,
                replace_apt=replace_apt,
                inspector=config['inspector'] if config else None,
                operator_configuration=config,
                operator_configuration_sha256=configuration_digest() if config else None)

def effective_requests(original, selected):
    if selected is None:
        return original
    result = []
    for dep in original:
        if dep['name'] in selected['replace_apt']:
            if dep['checks']:
                raise ValueError('non-wildcard reference substitution: ' + dep['name'])
        else:
            result.append(dep)
    # Explicit tools/runtime required by the verified reference overlay and its
    # loader/consumer preflight. APT resolves the complete Debian closure.
    if selected['groups']:
        existing = {d['name'] for d in result}
        runtime = KERNEL_RUNTIME_APT if selected['family'] in KERNEL_FAMILIES else SDK_RUNTIME_APT
        for name in runtime:
            if name not in existing:
                result.append(dict(name=name, checks=[]))
    return sorted(result, key=lambda d:d['name'])

def relative(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or str(p) != name.rstrip('/'):
        raise ValueError('unsafe archive path: ' + name)
    return p

def parent_safe(root, path):
    rel = path.relative_to(root)
    p = root
    for component in rel.parts[:-1]:
        p = p / component
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise ValueError('symlink/non-directory parent: ' + str(p))
        p.mkdir(exist_ok=True)

def safe_member(root, member, stream, name, identical=False):
    rel = relative(name)
    if rel.parts[0] != 'usr':
        raise ValueError('reference payload outside /usr: ' + name)
    dest = root / str(rel)
    parent_safe(root, dest)
    if member.isdir():
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            raise ValueError('directory collision: ' + name)
        dest.mkdir(exist_ok=True)
        return
    if not (member.isfile() or member.issym()) or member.mode & 0o7000:
        raise ValueError('unsupported archive type/mode: ' + name)
    if member.issym():
        target = PurePosixPath(member.linkname)
        if target.is_absolute():
            raise ValueError('absolute reference symlink: ' + name)
        normalized = Path(os.path.normpath(str(rel.parent / target)))
        if normalized.parts[0] != 'usr' or '..' in normalized.parts:
            raise ValueError('escaping reference symlink: ' + name)
    if dest.exists() or dest.is_symlink():
        if identical and member.isfile() and dest.is_file() and not dest.is_symlink():
            data = stream.read()
            if hashlib.sha256(data).hexdigest() == digest(dest) and stat.S_IMODE(dest.stat().st_mode) == member.mode:
                return
        raise ValueError('reference payload collision: ' + name)
    if member.issym():
        dest.symlink_to(member.linkname)
    else:
        with dest.open('xb') as f:
            shutil.copyfileobj(stream, f)
        dest.chmod(member.mode)

def extract_verified(artifact, root, *, uapi_prefix=None):
    # Signature verification is performed first by inspect(); consume the same
    # held archive whose complete hash matches that independently verified input.
    with Path(artifact['Path']).open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != artifact['SHA256']:
            raise ValueError('archive changed before extraction')
        f.seek(0)
        child = subprocess.Popen(['zstd','-qdc'], stdin=f, stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=child.stdout, mode='r|') as archive:
                count = 0
                for member in archive:
                    relative(member.name)
                    if member.name.startswith('.peipkg/'):
                        continue
                    if uapi_prefix is not None:
                        if not member.name.startswith(uapi_prefix + '/'):
                            continue
                        name = 'usr/include/pkm/' + member.name[len(uapi_prefix)+1:]
                    else:
                        name = member.name
                    source = archive.extractfile(member) if member.isfile() else None
                    safe_member(root, member, source, name, identical=uapi_prefix is not None)
                    count += 1
            if child.wait() != 0:
                raise ValueError('reference archive decompression failed')
            if not count:
                raise ValueError('empty reference payload/UAPI selection')
            f.seek(0)
            if hashlib.file_digest(f,'sha256').hexdigest() != artifact['SHA256']:
                raise ValueError('archive changed during extraction')
        finally:
            child.stdout.close()
            if child.poll() is None:
                child.kill(); child.wait()

def inspect(selected, output):
    inspector = selected['inspector']
    if digest(inspector['path']) != inspector['sha256'] or digest(inspector['key']) != inspector['key_sha256']:
        raise ValueError('reference verifier/trust identity changed')
    inputs=[]; receipts=[]
    for group in selected['groups']:
        if digest(group['receipt']) != group['receipt_sha256'] or digest(group['audit']) != group['audit_sha256']:
            raise ValueError('reference receipt/audit changed')
        receipt=json.loads(Path(group['receipt']).read_text())
        if receipt['Environment'] != 'debian' or receipt['RecipeRef'] != group['recipe_ref'] or receipt['Source'] != group['source']:
            raise ValueError('reference provider or source identity mismatch')
        audited={x['Path']:x for x in map(json.loads,Path(group['audit']).read_text().splitlines())}
        byname={a['Name']:a for a in receipt['Artifacts']}
        for a in group['artifacts'] + [group['source_artifact']]:
            if byname.get(a['Name']) != a or a['Version'] != group['version']:
                raise ValueError('artifact not bound by selected receipt')
            if not audited.get(a['Path'],{}).get('Signed') or audited[a['Path']]['Environment'] != 'debian':
                raise ValueError('missing independent reference archive audit')
            if digest(a['Path']) != a['SHA256']:
                raise ValueError('changed reference artifact')
            inputs.append(dict(Family=group['family'],Environment='debian',Path=a['Path']))
        receipts.append(receipt)
    ip=output/'inspection-inputs.json'; ip.write_bytes(encoded(inputs))
    p=subprocess.run([inspector['path'],str(ip)],capture_output=True,check=True)
    rows=[json.loads(x) for x in p.stdout.splitlines()]
    if len(rows)!=len(inputs) or any(not r['Signed'] for r in rows) or {r['Path'] for r in rows}!={r['Path'] for r in inputs}:
        raise ValueError('incomplete signature verification')
    (output/'signed-audit.jsonl').write_bytes(p.stdout)
    return receipts

def inventory(root):
    result={}
    for p in sorted(root.rglob('*')):
        rel=str(p.relative_to(root))
        if p.is_symlink():result[rel]={'link':os.readlink(p)}
        elif p.is_file():result[rel]={'sha256':digest(p),'mode':stat.S_IMODE(p.stat().st_mode)}
        elif p.is_dir():result[rel]={'directory':True}
        else:raise ValueError('special reference file')
    return result

def build_overlay(selected, directory):
    directory.mkdir(exist_ok=False)
    receipts=inspect(selected,directory)
    root=directory/'root';root.mkdir()
    for group in selected['groups']:
        for artifact in group['artifacts']:extract_verified(artifact,root)
        if group.get('uapi_prefix'):
            extract_verified(group['source_artifact'],root,uapi_prefix=group['uapi_prefix'])
    if selected['groups']:
        libroot=root/'usr/lib/x86_64-linux-peios/pkgconfig'
        for pc in sorted(libroot.glob('*.pc')):
            dest=root/'usr/lib/pkgconfig'/pc.name;parent_safe(root,dest)
            if dest.exists() or dest.is_symlink():raise ValueError('pkgconfig compatibility collision')
            dest.symlink_to('../x86_64-linux-peios/pkgconfig/'+pc.name)
    record=dict(schema=1,selection=selected,receipt_evidence=receipts,payload=inventory(root),
                adapter_sha256=digest(__file__),signature_audit_sha256=digest(directory/'signed-audit.jsonl'))
    (directory/'reference-prerequisites.json').write_bytes(encoded(record))
    return record

def check_collisions(root, overlay):
    # Inspect the exact Debian export before any copy. Existing ordinary
    # directories may merge; no file/symlink replacement is authorized.
    for p in sorted(overlay.rglob('*')):
        rel=p.relative_to(overlay);q=root/rel
        prefix=root
        for part in rel.parts[:-1]:
            prefix=prefix/part
            if prefix.is_symlink():raise ValueError('Debian symlink parent: '+str(rel))
        if not q.exists() and not q.is_symlink():continue
        if p.is_dir() and not p.is_symlink() and q.is_dir() and not q.is_symlink():continue
        raise ValueError('Debian/reference collision: '+str(rel))

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
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
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
versions={g['family']:g['version'].rsplit('-',1)[0] for g in record['selection']['groups']}
if 'org.rust-lang.rust' in versions:
 expected=versions['org.rust-lang.rust']
 for name in ['rustc','cargo','rustdoc']:
  output=run(['/usr/bin/'+name,'--version'])
  if output.split()[:2]!=[name,expected]:raise SystemExit('wrong reference tool: '+name)
 with tempfile.TemporaryDirectory(prefix='reference-consumer-') as td:
  td=Path(td);src=td/'main.rs';exe=td/'main'
  src.write_text('fn main() { let x=std::thread::spawn(|| vec![1u32,2,3].iter().sum::<u32>()); assert_eq!(x.join().unwrap(),6); }\n')
  run(['/usr/bin/rustc',str(src),'-o',str(exe)]);run([str(exe)])
  if any(a['Name']=='org.rust-lang.rust-std-x86-64-unknown-linux-musl'
         for g in record['selection']['groups'] for a in g['artifacts']):
   musl=td/'musl'
   run(['/usr/bin/rustc',str(src),'--target=x86_64-unknown-linux-musl',
        '-C','target-feature=+crt-static','-C','relocation-model=pic',
        '-C','link-arg=-static-pie','-C','link-arg=-Wl,-z,relro,-z,now',
        '-C','link-arg=-Wl,-z,pack-relative-relocs','-o',str(musl)])
   run([str(musl)])
   dynamic=run(['/usr/bin/readelf','-dW',str(musl)])
   header=run(['/usr/bin/readelf','-hW',str(musl)])
   segments=run(['/usr/bin/readelf','-lW',str(musl)])
   if ('(NEEDED)' in dynamic or '(RELR)' not in dynamic or 'NOW' not in dynamic
       or not re.search(r'Type:\s+DYN\b',header) or 'INTERP' in segments
       or 'GNU_RELRO' not in segments):
    raise SystemExit('musl static consumer lacks required linkage/hardening')
# The kernel's pinned Rust-for-Linux toolchain. Kbuild compiles core from the
# rust-src at RUST_LIB_SRC, so it must be this compiler's own, at the multiarch
# path the kernel's Debian env file names.
if 'org.rust-lang.rust-1.83' in versions:
 expected=versions['org.rust-lang.rust-1.83']
 for name in ['rustc','rustdoc']:
  output=run(['/usr/bin/'+name,'--version'])
  if output.split()[:2]!=[name,expected]:raise SystemExit('wrong reference tool: '+name)
 run(['/usr/bin/rustfmt','--version'])
 if not Path('/usr/lib/x86_64-linux-peios/rustlib/src/rust/library/core/src/lib.rs').is_file():
  raise SystemExit('reference rust-src missing')
 with tempfile.TemporaryDirectory(prefix='reference-consumer-') as td:
  td=Path(td);src=td/'main.rs';exe=td/'main'
  src.write_text('fn main() { let x=std::thread::spawn(|| vec![1u32,2,3].iter().sum::<u32>()); assert_eq!(x.join().unwrap(),6); }\n')
  run(['/usr/bin/rustc',str(src),'-o',str(exe)]);run([str(exe)])
if 'io.github.rust-lang.bindgen' in versions:
 expected=versions['io.github.rust-lang.bindgen']
 if run(['/usr/bin/bindgen','--version']).split()[:2]!=['bindgen',expected]:
  raise SystemExit('wrong reference tool: bindgen')
 # bindgen loads libclang at run time instead of linking it, so the readelf/ldd
 # pass above cannot see that dependency. Generating a binding proves it.
 with tempfile.TemporaryDirectory(prefix='reference-bindgen-') as td:
  header=Path(td)/'probe.h';header.write_text('struct pekit_reference_probe { int value; };\n')
  if 'pekit_reference_probe' not in run(['/usr/bin/bindgen',str(header)]):
   raise SystemExit('bindgen produced no binding')
for library,pc,header in [('dev.peios.libpeios','peios','peios.h'),('dev.peios.librsi','rsi','rsi.h')]:
 if library not in versions:continue
 if run(['/usr/bin/pkg-config','--modversion',pc]).strip()!=versions[library]:raise SystemExit('wrong SDK version')
 flags=shlex.split(run(['/usr/bin/pkg-config','--cflags','--libs',pc]))
 with tempfile.TemporaryDirectory(prefix='reference-abi-') as td:
  td=Path(td);src=td/'main.c';exe=td/'main'
  src.write_text('#include <'+header+'>\nint main(void) { return 0; }\n')
  run(['/usr/bin/gcc',str(src),'-Wl,--no-as-needed',*flags,'-o',str(exe)]);run([str(exe)])
print(json.dumps(dict(passed=True,checks=checks,resolved_runtime_sha256=runtime),sort_keys=True))
'''

def install_container(container, selected, directory):
    record=build_overlay(selected,directory)
    subprocess.run(['docker','exec','-i',container,'python3','-c',COLLISION_CHECK],
                   input=encoded(record['payload']),check=True)
    subprocess.run(['docker','cp',str(directory/'root/usr')+'/.',container+':/usr/'],check=True)
    # This file is generated coordinator policy, not a payload permitted to
    # overwrite arbitrary configuration. The collision guard checked it first.
    config=b'/usr/lib/x86_64-linux-peios\n'
    subprocess.run(['docker','exec','-i',container,'python3','-c',
        "from pathlib import Path; import sys; p=Path('/etc/ld.so.conf.d/pekit-reference.conf'); p.parent.mkdir(parents=True,exist_ok=True); p.open('xb').write(sys.stdin.buffer.read())"],input=config,check=True)
    subprocess.run(['docker','exec',container,'/sbin/ldconfig'],check=True)
    result=subprocess.run(['docker','exec','-i',container,'python3','-c',RUNTIME_CHECK],
                          input=encoded(record),capture_output=True,check=True)
    check=json.loads(result.stdout)
    if check.get('passed') is not True:raise ValueError('reference runtime not validated')
    record['runtime']=check
    evidence=encoded(record)
    subprocess.run(['docker','exec','-i',container,'python3','-c',
        "from pathlib import Path; import sys; p=Path('/usr/share/pekit-reference/reference-prerequisites.json'); p.parent.mkdir(parents=True,exist_ok=True); p.open('xb').write(sys.stdin.buffer.read())"],input=evidence,check=True)
    (directory/'reference-prerequisites.json').write_bytes(evidence)
    return record
