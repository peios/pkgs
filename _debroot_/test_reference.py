"""Debian root prerequisite policy and overlay safety tests.

Hermetic: no network, docker, repository or real toolchain is required. The
upstream fetch is exercised against a local archive with a patched pin; real
signature verification is covered by the integration run documented on
PEI-1156.
"""
import io, json, os, subprocess, sys, tarfile, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
D = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(D))
import reference as r
import prepare as p

INDEX = {'dev.peios.libpeios', 'dev.peios.libpeios-devel', 'dev.peios.kernel-headers',
         'io.github.rust-lang.bindgen'}


def dep(name, *checks):
    return dict(name=name, checks=[list(c) for c in checks])


class Selection(unittest.TestCase):

    def test_toolchain_scope(self):
        self.assertIsNone(r.selection('arbitrary', 'build-main', [], INDEX))
        self.assertRaises(ValueError, r.selection, 'dev.peios.resolvd', 'build-arbitrary', [], INDEX)
        for family in r.RUST_FAMILIES:
            for target in r.TARGETS:
                self.assertEqual(r.selection(family, target, [], INDEX)['toolchain'], 'rust-1.98.1')
        # Recipes outside the seed never build here and get no overlay.
        self.assertIsNone(r.selection('dev.peios.authd', 'build-main', [], INDEX))

    def test_kernel_scope(self):
        # Only the two targets that run rustc receive the pinned toolchain;
        # every other kernel target is reviewed and keeps a plain Debian root.
        for target in r.KERNEL_TOOLCHAIN_TARGETS:
            self.assertEqual(r.selection('dev.peios.kernel', target, [], INDEX)['toolchain'], 'rust-1.83.0')
        for target in r.KERNEL_TARGETS - r.KERNEL_TOOLCHAIN_TARGETS:
            self.assertIsNone(r.selection('dev.peios.kernel', target, [], INDEX))
        self.assertRaises(ValueError, r.selection, 'dev.peios.kernel', 'build-arbitrary', [], INDEX)
        self.assertRaises(ValueError, r.selection, 'dev.peios.kernel', 'build-main', [], INDEX)

    def test_catalogue_routing(self):
        deps = [dep('gcc'), dep('dev.peios.libpeios-devel', ('>=', '0.5.0')), dep('python3.13')]
        s = r.selection('arbitrary', 'build-main', deps, INDEX)
        self.assertIsNone(s['toolchain'])
        self.assertEqual(s['catalogue'], [deps[1]])
        effective = {d['name'] for d in r.effective_requests(deps, s, INDEX)}
        self.assertIn('gcc', effective)
        self.assertIn('python3.13', effective)
        self.assertNotIn('dev.peios.libpeios-devel', effective)
        self.assertTrue(set(r.RUNTIME_APT) <= effective)
        # A reverse-DNS name the repository lacks fails here, not in apt.
        with self.assertRaisesRegex(ValueError, 'not in the repository'):
            r.selection('arbitrary', 'build-main', [dep('dev.peios.missing')], INDEX)
        self.assertIsNone(r.selection('arbitrary', 'build-main', [dep('gcc')], INDEX))
        # The repository's unqualified historical names never shadow Debian's.
        s = r.selection('arbitrary', 'build-main', [dep('debugedit')], INDEX | {'debugedit'})
        self.assertIsNone(s)

    def test_toolchain_substitution(self):
        s = r.selection('dev.peios.resolvd', 'build-main', [], INDEX)
        original = [dep('cargo'), dep('gcc', ('>=', '16')), dep('rustc'), dep('rustfmt')]
        effective = r.effective_requests(original, s, INDEX)
        self.assertFalse({'cargo', 'rustc', 'rustfmt'} & {x['name'] for x in effective})
        self.assertIn(original[1], effective)
        self.assertRaises(ValueError, r.effective_requests, [dep('rustc', ('>=', '1.98'))], s, INDEX)
        # Without a toolchain, Debian's own rustc stays.
        s = r.selection('arbitrary', 'build-main', [dep('dev.peios.libpeios')], INDEX)
        self.assertIn('rustc', {x['name'] for x in r.effective_requests([dep('rustc')], s, INDEX)})

    def test_constraint_rendering(self):
        self.assertEqual(r.constraint([]), '*')
        self.assertEqual(r.constraint([['>=', '0.5.0'], ['<', '1']]), '>= 0.5.0, < 1')

    def test_pins_cover_every_toolchain_archive(self):
        for name, toolchain in r.TOOLCHAINS.items():
            for archive, components in toolchain['archives']:
                self.assertRegex(r.RUST_ARCHIVES[archive], '^[0-9a-f]{64}$')
                self.assertTrue(components)
        self.assertTrue(r.RUST_KEY.is_file())


class Safety(unittest.TestCase):

    def setUp(self):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PEKIT_')}
        context = patch.dict(os.environ, environment, clear=True)
        context.start()
        self.addCleanup(context.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / 'src'
        self.dst = self.root / 'dst'
        self.src.mkdir()
        self.dst.mkdir()

    def entry(self, name, data=b'x', mode=0o644, link=None):
        path = self.src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if link is not None:
            path.symlink_to(link)
        else:
            path.write_bytes(data)
            path.chmod(mode)
        return path

    def test_paths(self):
        for name in ['/usr/a', '../x', 'usr/../x', 'usr//x', 'usr/./x', 'etc/passwd']:
            with self.subTest(name=name):
                self.assertRaises(ValueError, r.relative, name)

    def test_links_and_modes(self):
        for name, kwargs in [('usr/a', dict(link='/etc/passwd')), ('usr/b', dict(link='../../../escape')),
                             ('usr/c', dict(mode=0o4755))]:
            with self.subTest(name=name):
                source = self.entry(name, **kwargs)
                self.assertRaises(ValueError, r.place, self.dst, source, name)
        good = self.entry('usr/lib/libx.so', link='libx.so.1')
        r.place(self.dst, good, 'usr/lib/libx.so')
        self.assertEqual(os.readlink(self.dst / 'usr/lib/libx.so'), 'libx.so.1')

    def test_symlink_parent(self):
        (self.dst / 'usr').symlink_to('/tmp')
        self.assertRaises(ValueError, r.place, self.dst, self.entry('usr/a'), 'usr/a')

    def test_collisions(self):
        source = self.entry('usr/a', mode=0o755)
        r.place(self.dst, source, 'usr/a')
        self.assertEqual((self.dst / 'usr/a').stat().st_mode & 0o777, 0o755)
        self.assertRaises(ValueError, r.place, self.dst, source, 'usr/a')

    def test_catalogue_copies_only_owned_files_and_subtrees(self):
        scratch = self.root / 'work' / 'scratch'
        for name in ['usr/include/pkm/psb.h', 'usr/include/linux/fs.h', 'usr/include/peios.h',
                     'usr/lib/x86_64-linux-peios/libc.so.6']:
            path = scratch / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        owned = {'dev.peios.kernel-headers': ['/usr', '/usr/include', '/usr/include/pkm',
                                              '/usr/include/pkm/psb.h', '/usr/include/linux', '/usr/include/linux/fs.h'],
                 'dev.peios.libpeios-devel': ['/usr', '/usr/include', '/usr/include/peios.h']}

        def fake(cmd, **kwargs):
            if cmd[0] == 'peipkg-compose':
                (self.root / 'work' / 'root.lock.toml').write_text('lock')
                return subprocess.CompletedProcess(cmd, 0, '', '')
            if cmd[3] == 'list':
                return subprocess.CompletedProcess(cmd, 0, 'dev.peios.kernel-headers  1-1  x86_64\n'
                                                   'dev.peios.libpeios-devel  0.5.0-1  x86_64\n'
                                                   'org.gnu.glibc  2.44-7  x86_64\n', '')
            return subprocess.CompletedProcess(cmd, 0, '\n'.join(owned[cmd[4]]) + '\n', '')
        with patch.object(r.subprocess, 'run', side_effect=fake):
            record = r.install_catalogue([dep('dev.peios.kernel-headers'), dep('dev.peios.libpeios-devel')],
                                         self.dst, Path('/snapshot'), '0' * 64, self.root / 'work')
        self.assertTrue((self.dst / 'usr/include/pkm/psb.h').is_file())
        self.assertTrue((self.dst / 'usr/include/peios.h').is_file())
        # Linux UAPI comes from Debian; the closure's glibc never lands.
        self.assertFalse((self.dst / 'usr/include/linux').exists())
        self.assertFalse((self.dst / 'usr/lib').exists())
        self.assertEqual([x['version'] for x in record['packages']], ['1-1', '0.5.0-1'])

    def test_fetch_rejects_changed_cache_and_unpinned_download(self):
        cache = self.root / 'cache'
        cache.mkdir()
        name = 'rust-src-1.83.0.tar.xz'
        (cache / name).write_bytes(b'tampered')
        self.assertRaisesRegex(ValueError, 'changed', r.fetch, name, cache)
        (cache / name).unlink()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        with patch.object(r.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(b'not the pinned bytes')):
            self.assertRaisesRegex(ValueError, 'pin', r.fetch, name, cache)
        self.assertFalse((cache / name).exists())

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
        recipe = self.root / 'dev.peios.resolvd'
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

    def lifecycle(self, overlay, fail=None):
        job = self.root / 'job'
        store = self.root / 'store'
        out = self.root / 'record'
        job.mkdir()
        store.mkdir()
        state = dict(running=False, installed=False, removed=False)
        selected = {'toolchain': 'rust-1.98.1', 'catalogue': []} if overlay else None

        def run(*args, capture=False):
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

        def install(container, sel, directory, cache):
            self.assertTrue(state['running'])
            self.assertTrue(state['installed'])
            self.assertEqual(cache, store / 'upstream')
            if fail == 'overlay':
                raise ValueError('overlay failed')
            return {'runtime': {'passed': True}}
        with patch.dict(os.environ, {'PEKIT_RECIPE_ROOT': '/recipe/dev.peios.resolvd' if overlay else '/recipe/other', 'PEKIT_COMMAND': 'build', 'PEKIT_TARGET': 'main'}), \
                patch.object(p, 'run', side_effect=run), patch.object(r, 'selection', return_value=selected), \
                patch.object(r, 'effective_requests', return_value=[]), \
                patch.object(r, 'install_container', side_effect=install) as hook:
            if fail:
                self.assertRaises((ValueError, subprocess.CalledProcessError), p.acquire, job, store, [], 'policy', out)
            else:
                manifest = p.acquire(job, store, [], 'policy', out)
                self.assertEqual('reference_sha256' in manifest, overlay)
            self.assertEqual(hook.call_count, 1 if overlay and fail != 'apt' else 0)
        self.assertTrue(state['removed'])

    def test_overlay_running_lifecycle(self):
        self.lifecycle(True)

    def test_ordinary_stopped_lifecycle(self):
        self.lifecycle(False)

    def test_apt_failure_removes_container(self):
        self.lifecycle(True, 'apt')

    def test_overlay_failure_removes_container(self):
        self.lifecycle(True, 'overlay')


if __name__ == '__main__':
    unittest.main(verbosity=2)
