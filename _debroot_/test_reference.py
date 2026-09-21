"""Portable reference adapter tests with private temporary synthetic policy.

No operator configuration, qualified archive, or real trust key is required.
The reject-only verifier fixture tests rejection propagation, not cryptographic
signature validation; genuine signed inputs have a separate integration audit.
"""
import importlib.util, io, json, os, stat, sys, tarfile, tempfile, unittest
from pathlib import Path
D = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(D))
import reference as r
import prepare as p

class Safety(unittest.TestCase):

    def setUp(self):
        from unittest.mock import patch
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PEKIT_')}
        context = patch.dict(os.environ, environment, clear=True)
        context.start()
        self.addCleanup(context.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        r._job_configuration = None
        self.original_config = r.CONFIG
        r.CONFIG = self.root / 'selection.json'
        r.configuration.cache_clear()
        self.inspector = self.root / 'reject-unsigned.py'
        self.inspector.write_text('#!' + sys.executable + '\nimport sys\nraise SystemExit(23)\n')
        self.inspector.chmod(448)
        self.key = self.root / 'test-only-key'
        self.key.write_bytes(b'not a production key')
        config = {'schema': 1, 'inspector': {'path': str(self.inspector), 'sha256': r.digest(self.inspector), 'key': str(self.key), 'key_sha256': r.digest(self.key)}, 'groups': {'rust': {'family': 'org.rust-lang.rust', 'artifacts': [{'Name': 'org.rust-lang.rustc'}]}, 'libpeios-current': {'family': 'dev.peios.libpeios', 'artifacts': [{'Name': 'dev.peios.libpeios-devel'}]}, 'rust-musl': {'family': 'org.rust-lang.rust', 'artifacts': [{'Name': 'org.rust-lang.rust-std-x86-64-unknown-linux-musl'}]}, 'rust-1.83': {'family': 'org.rust-lang.rust-1.83', 'artifacts': [{'Name': 'org.rust-lang.rustc'}]}, 'bindgen': {'family': 'io.github.rust-lang.bindgen', 'artifacts': [{'Name': 'io.github.rust-lang.bindgen'}]}}}
        r.CONFIG.write_text(json.dumps(config))
        r.CONFIG.chmod(384)

    def tearDown(self):
        r._job_configuration = None
        r.CONFIG = self.original_config
        r.configuration.cache_clear()
        self.temp.cleanup()

    def member(self, name='usr/include/a.h', kind=tarfile.REGTYPE, link='', mode=420):
        m = tarfile.TarInfo(name)
        m.type = kind
        m.linkname = link
        m.mode = mode
        m.size = 1
        return m

    def put(self, m, data=b'x', identical=False):
        r.safe_member(self.root, m, io.BytesIO(data), m.name, identical)

    def test_scope(self):
        self.assertIsNone(r.selection('arbitrary', 'build-main'))
        self.assertRaises(ValueError, r.selection, 'dev.peios.authd', 'build-arbitrary')
        self.assertEqual(len(r.selection('dev.peios.eventd', 'build-main')['groups']), 2)
        self.assertEqual(len(r.selection('dev.peios.authd', 'build-vendor')['groups']), 1)
        self.assertEqual(len(r.selection('dev.peios.authd', 'test-main')['groups']), 2)
        self.assertEqual(r.selection('dev.peios.loregd', 'build-vendor')['groups'], [])
        self.assertEqual(r.selection('dev.peios.peipkg', 'build-vendor')['groups'], [])
        for family in r.SDK_FAMILIES:
            for target in ['build-main', 'test-main']:
                self.assertEqual([g['family'] for g in r.selection(family, target)['groups']], ['org.rust-lang.rust', 'dev.peios.libpeios'])
        self.assertEqual([a['Name'] for a in r.selection('dev.peios.peios-installer', 'build-main')['groups'][1]['artifacts']], ['org.rust-lang.rust-std-x86-64-unknown-linux-musl'])
        self.assertEqual(len(r.selection('dev.peios.peios-installer', 'build-vendor')['groups']), 1)

    def test_kernel_scope(self):
        # Only the two targets that run rustc and bindgen receive the pinned
        # toolchain, and nothing else; every other kernel target is reviewed
        # and keeps a plain Debian root.
        for target in ['build-kunit', 'build-kernel']:
            s = r.selection('dev.peios.kernel', target)
            self.assertEqual([g['family'] for g in s['groups']], ['org.rust-lang.rust-1.83', 'io.github.rust-lang.bindgen'])
            self.assertEqual(s['image'], 'debian:trixie')
        for target in r.KERNEL_TARGETS - r.KERNEL_TOOLCHAIN_TARGETS:
            self.assertIsNone(r.selection('dev.peios.kernel', target))
        self.assertRaises(ValueError, r.selection, 'dev.peios.kernel', 'build-arbitrary')
        # A SDK-family target name is not thereby reviewed for the kernel.
        self.assertRaises(ValueError, r.selection, 'dev.peios.kernel', 'build-main')

    def test_kernel_stays_on_trixie(self):
        # The 1.83 toolchain links trixie's libLLVM-18; moving the kernel to sid
        # would quietly strand it.
        from unittest.mock import patch
        self.assertNotIn('dev.peios.kernel', r.SID_FAMILIES)
        with patch.dict(os.environ, {'PEKIT_RECIPE_ROOT': '/w/dev.peios.kernel'}):
            self.assertEqual(p.selected_image(), 'debian:trixie')

    def test_kernel_requires_both_groups(self):
        config = json.loads(r.CONFIG.read_text())
        del config['groups']['bindgen']
        r.CONFIG.write_text(json.dumps(config))
        r.configuration.cache_clear()
        with self.assertRaisesRegex(ValueError, 'not qualified/selected: bindgen'):
            r.selection('dev.peios.kernel', 'build-kernel')

    def test_kernel_substitution(self):
        s = r.selection('dev.peios.kernel', 'build-kernel')
        original = [{'name': 'clang-18', 'checks': []}, {'name': 'rustc', 'checks': []}, {'name': 'bindgen', 'checks': []}]
        effective = {x['name'] for x in r.effective_requests(original, s)}
        self.assertFalse({'rustc', 'bindgen', 'cargo', 'rustfmt'} & effective)
        self.assertIn('clang-18', effective)
        # The kernel's rustc needs LLVM 18 at run time, not the SDK's LLVM 23.
        self.assertIn('libllvm18', effective)
        self.assertNotIn('libllvm23', effective)
        sdk = {x['name'] for x in r.effective_requests([], r.selection('dev.peios.authd', 'build-main'))}
        self.assertEqual(sdk, set(r.SDK_RUNTIME_APT))

    def test_substitution(self):
        s = r.selection('dev.peios.authd', 'build-main')
        original = [{'name': 'cargo', 'checks': []}, {'name': 'gcc', 'checks': [['>=', '16']]}, {'name': 'rustc', 'checks': []}]
        effective = r.effective_requests(original, s)
        self.assertFalse({'cargo', 'rustc'} & {x['name'] for x in effective})
        self.assertIn(original[1], effective)
        self.assertEqual(original[0]['name'], 'cargo')
        self.assertRaises(ValueError, r.effective_requests, [{'name': 'rustc', 'checks': [['>=', '1.98']]}], s)

    def test_paths(self):
        for name in ['/usr/a', '../x', 'usr/../x', 'usr//x', 'usr/./x', 'etc/passwd', 'usr']:
            if name == 'usr':
                continue
            with self.subTest(name=name):
                self.assertRaises(ValueError, self.put, self.member(name))

    def test_links_special_modes(self):
        for m in [self.member(kind=tarfile.LNKTYPE), self.member(kind=tarfile.CHRTYPE), self.member(kind=tarfile.SYMTYPE, link='/etc/passwd'), self.member(kind=tarfile.SYMTYPE, link='../../../escape'), self.member(mode=2541)]:
            with self.subTest(m=m):
                self.assertRaises(ValueError, self.put, m)

    def test_symlink_parent(self):
        (self.root / 'usr').symlink_to('/tmp')
        self.assertRaises(ValueError, self.put, self.member())

    def test_collisions(self):
        self.put(self.member())
        self.assertRaises(ValueError, self.put, self.member())
        self.put(self.member(), identical=True)
        self.assertRaises(ValueError, self.put, self.member(), b'y', True)

    def test_debian_collisions(self):
        overlay = self.root / 'overlay'
        debian = self.root / 'debian'
        overlay.mkdir()
        debian.mkdir()
        (overlay / 'usr').mkdir()
        (debian / 'usr').mkdir()
        (overlay / 'usr/a').write_text('x')
        r.check_collisions(debian, overlay)
        (debian / 'usr/a').write_text('x')
        self.assertRaises(ValueError, r.check_collisions, debian, overlay)
        (debian / 'usr/a').unlink()
        (debian / 'usr').rmdir()
        (debian / 'usr').symlink_to('/tmp')
        self.assertRaises(ValueError, r.check_collisions, debian, overlay)

    def test_archive_hash_before_extract(self):
        f = self.root / 'package'
        f.write_bytes(b'not signed')
        self.assertRaises(ValueError, r.extract_verified, dict(Path=str(f), SHA256='0' * 64), self.root / 'out')

    def test_verifier_failure_rejects_unsigned_fixture(self):
        selected = r.selection('dev.peios.authd', 'build-vendor')
        g = selected['groups'][0].copy()
        artifact = self.root / 'bad.peipkg'
        artifact.write_bytes(b'not a signed archive')
        a = dict(Name='fixture', Version='1-1', Architecture='noarch', Path=str(artifact), SHA256=r.digest(artifact))
        receipt = self.root / 'receipt.json'
        receipt.write_text(json.dumps(dict(Environment='debian', RecipeRef='fixture', Source='fixture', Artifacts=[a])))
        audit = self.root / 'audit.jsonl'
        audit.write_text(json.dumps(dict(Path=str(artifact), Signed=True, Environment='debian')) + '\n')
        g.update(receipt=str(receipt), receipt_sha256=r.digest(receipt), audit=str(audit), audit_sha256=r.digest(audit), recipe_ref='fixture', source='fixture', version='1-1', artifacts=[a], source_artifact=a)
        selected['groups'] = [g]
        import subprocess
        self.assertRaises(subprocess.CalledProcessError, r.inspect, selected, self.root)

    def test_replay_record_binds_overlay(self):
        record = self.root / 'record'
        record.mkdir()
        (record / 'installed.tsv').write_bytes(b'apt')
        (record / 'reference-prerequisites.json').write_bytes(b'original')
        manifest = dict(schema=p.SCHEMA, requests=[], policy_sha256='policy', host_architecture=p.platform.machine(), root_sha256='0' * 64, installed_sha256=r.digest(record / 'installed.tsv'), reference_sha256=r.digest(record / 'reference-prerequisites.json'))
        (record / 'debian-root.json').write_text(json.dumps(manifest))
        self.assertEqual(p.load_record(record, [], 'policy'), manifest)
        (record / 'reference-prerequisites.json').write_bytes(b'changed')
        self.assertRaises(ValueError, p.load_record, record, [], 'policy')

    def test_offline_root_overlay_binding(self):
        root = self.root / 'base'
        (root / 'tmp').mkdir(parents=True)
        evidence = root / 'usr/share/pekit-reference/reference-prerequisites.json'
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b'reference')
        (root / 'tmp/dependencies.tsv').write_bytes(b'apt')
        archive = self.root / 'root.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            t.add(root, arcname='.')
        digest = r.digest(archive)
        archive.rename(self.root / (digest + '.tar.gz'))
        manifest = dict(root_sha256=digest, installed_sha256=r.digest(root / 'tmp/dependencies.tsv'), reference_sha256=r.digest(evidence))
        p.restore(self.root, manifest, self.root / 'restored')
        self.assertEqual((self.root / 'restored/usr/share/pekit-reference/reference-prerequisites.json').read_bytes(), b'reference')
        manifest['reference_sha256'] = '0' * 64
        self.assertRaises(ValueError, p.restore, self.root, manifest, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())

    def test_dependency_record_capture(self):
        from unittest.mock import patch
        recipe = self.root / 'dev.peios.authd'
        job = self.root / 'job'
        environ = {'PEKIT_RECIPE_ROOT': str(recipe), 'PEKIT_COMMAND': 'build', 'PEKIT_TARGET': 'vendor', 'PEKIT_DEPENDENCIES': 'cargo *', 'PEKIT_JOB_STATE': str(job), 'PEKIT_SANDBOX_ROOT': str(self.root / 'sandbox')}
        with patch.dict(os.environ, environ):
            deps = p.requests('cargo *')
            policy = p.policy_id()
            key = p.hashlib.sha256(p.encoded({'requests': deps, 'policy': policy})).hexdigest()
            cached = job / 'debian-roots' / key
            cached.mkdir(parents=True)
            (cached / 'installed.tsv').write_bytes(b'apt')
            (cached / 'reference-prerequisites.json').write_bytes(b'ref')
            manifest = dict(schema=p.SCHEMA, requests=deps, policy_sha256=policy, host_architecture=p.platform.machine(), root_sha256='0' * 64, installed_sha256=r.digest(cached / 'installed.tsv'), reference_sha256=r.digest(cached / 'reference-prerequisites.json'))
            (cached / 'debian-root.json').write_text(json.dumps(manifest))
            with patch.object(p, 'restore') as restore, patch.object(p, 'acquire') as acquire:
                p.prepare()
                acquire.assert_not_called()
                restore.assert_called_once()
            capture = job / 'dependencies/build-vendor'
            self.assertEqual((capture / 'reference-prerequisites.json').read_bytes(), b'ref')
            self.assertEqual(json.loads((capture / 'debian-root.json').read_text()), manifest)

    def test_private_operator_config(self):
        r.CONFIG = self.root / 'selection.json'
        r.configuration.cache_clear()
        r.CONFIG.write_text('{"schema":1}')
        r.CONFIG.chmod(420)
        self.assertRaises(ValueError, r.configuration)
        r.CONFIG.chmod(384)
        self.assertEqual(r.configuration(), {'schema': 1})
        r.configuration.cache_clear()
        r.CONFIG.unlink()
        r.CONFIG.symlink_to(self.key)
        self.assertRaises(OSError, r.configuration)

    def lifecycle(self, overlay, fail=None):
        from unittest.mock import patch
        import subprocess
        job = self.root / 'job'
        store = self.root / 'store'
        out = self.root / 'record'
        job.mkdir()
        store.mkdir()
        state = dict(running=False, installed=False, removed=False)
        calls = []
        selected = {'groups': [{}]} if overlay else None

        def run(*args, capture=False):
            calls.append(args)
            if args[:3] == ('docker', 'image', 'inspect'):
                return '[{"Id":"sha256:exact","RepoDigests":["debian@sha256:exact"],"Architecture":"amd64","Os":"linux"}]'
            if args[:2] == ('docker', 'create'):
                self.assertEqual(args[4], 'sha256:exact')
                self.assertEqual(args[5:7], ('sleep', 'infinity') if overlay else ('sh', '-euc'))
                return 'container'
            if args[:2] == ('docker', 'start'):
                state['running'] = overlay
                state['installed'] = not overlay
                return ''
            if args[:2] == ('docker', 'exec'):
                self.assertTrue(state['running'])
                if fail == 'apt':
                    raise subprocess.CalledProcessError(1, args)
                state['installed'] = True
                return ''
            if args[:2] == ('docker', 'inspect'):
                return '0'
            if args[:2] == ('docker', 'cp'):
                Path(args[-1]).write_bytes(b'apt')
                return ''
            if args[:2] == ('docker', 'export'):
                self.assertTrue(state['installed'])
                Path(args[-1]).write_bytes(b'exported-root')
                return ''
            if args[:2] == ('docker', 'rm'):
                state['removed'] = True
            return ''

        def install(*args):
            self.assertTrue(state['running'])
            self.assertTrue(state['installed'])
            if fail == 'overlay':
                raise ValueError('overlay failed')
            return {'runtime': {'passed': True}}
        with patch.dict(os.environ, {'PEKIT_RECIPE_ROOT': '/recipe/dev.peios.authd' if overlay else '/recipe/other', 'PEKIT_COMMAND': 'build', 'PEKIT_TARGET': 'main'}), patch.object(p, 'run', side_effect=run), patch.object(r, 'selection', return_value=selected), patch.object(r, 'effective_requests', return_value=[]), patch.object(r, 'install_container', side_effect=install) as hook:
            if fail:
                self.assertRaises((ValueError, subprocess.CalledProcessError), p.acquire, job, store, [], 'policy', out)
            else:
                manifest = p.acquire(job, store, [], 'policy', out)
                self.assertEqual('reference_sha256' in manifest, overlay)
            self.assertEqual(hook.call_count, 1 if overlay and fail != 'apt' else 0)
        self.assertTrue(state['removed'])
        return calls

    def test_overlay_running_lifecycle(self):
        self.lifecycle(True)

    def test_ordinary_stopped_lifecycle(self):
        self.lifecycle(False)

    def test_apt_failure_removes_container(self):
        self.lifecycle(True, 'apt')

    def test_overlay_failure_removes_container(self):
        self.lifecycle(True, 'overlay')

    def test_replay_without_operator_config(self):
        from unittest.mock import patch
        replay = self.root / 'replay'
        record = replay / 'build-vendor'
        record.mkdir(parents=True)
        config_hash = r.configuration_digest()
        (record / 'debian-root.json').write_text(json.dumps({'reference_selection': {'operator_configuration_sha256': config_hash}}))
        with patch.dict(os.environ, {'PEKIT_RECIPE_ROOT': '/recipe/dev.peios.authd', 'PEKIT_COMMAND': 'build', 'PEKIT_TARGET': 'vendor'}):
            initial = p.policy_id()
            with patch.dict(os.environ, {'PEKIT_DEBIAN_REPLAY': str(replay)}), patch.object(r, 'configuration_digest', side_effect=AssertionError('must not read current private config')):
                self.assertEqual(p.policy_id(), initial)
if __name__ == '__main__':
    unittest.main(verbosity=2)
