"""Portable reference adapter tests with private temporary synthetic policy.

No operator configuration, qualified archive, or real trust key is required.
The reject-only verifier fixture tests rejection propagation, not cryptographic
signature validation; genuine signed inputs have a separate integration audit.
"""
import hashlib, importlib.util, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
import reference as r
import prepare as p

class JobSelection(unittest.TestCase):

    def setUp(self):
        from unittest.mock import patch
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PEKIT_')}
        context = patch.dict(os.environ, environment, clear=True)
        context.start()
        self.addCleanup(context.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.original = r.CONFIG
        r._job_configuration = None
        r.configuration.cache_clear()
        r.CONFIG = self.d / 'selection.json'
        self.write_config('A')
        self.job = self.d / 'job'
        self.job.mkdir()

    def tearDown(self):
        r.CONFIG = self.original
        r._job_configuration = None
        r.configuration.cache_clear()
        self.tmp.cleanup()

    def write_config(self, label):
        q = self.d / 'new'
        q.write_text(json.dumps(dict(schema=1, label=label)))
        q.chmod(384)
        q.replace(r.CONFIG)

    def bind(self, job=None):
        import fcntl
        job = job or self.job
        with (job / 'debian.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            r.bind_job_configuration(job, 'dev.peios.authd')
        return r.configuration()

    def test_active_job_unchanged_new_job_rolls(self):
        self.assertEqual(self.bind()['label'], 'A')
        before = (self.job / 'dependencies/reference-selection.json').read_bytes()
        self.write_config('B')
        self.assertEqual(self.bind()['label'], 'A')
        self.assertEqual((self.job / 'dependencies/reference-selection.json').read_bytes(), before)
        new = self.d / 'other-job'
        new.mkdir()
        self.assertEqual(self.bind(new)['label'], 'B')

    def test_reuse_without_current_operator(self):
        self.bind()
        r.CONFIG.unlink()
        self.assertEqual(self.bind()['label'], 'A')

    def test_corrupt_capture_rejected_without_fallback(self):
        self.bind()
        q = self.job / 'dependencies/reference-selection.json'
        j = json.loads(q.read_text())
        j['configuration']['label'] = 'corrupt'
        q.write_text(json.dumps(j))
        self.assertRaises(ValueError, self.bind)

    def test_other_family_capture_rejected(self):
        self.bind()
        self.assertRaises(ValueError, r.bind_job_configuration, self.job, 'dev.peios.eventd')

    def test_capture_symlink_rejected(self):
        self.bind()
        q = self.job / 'dependencies/reference-selection.json'
        q.unlink()
        q.symlink_to(r.CONFIG)
        self.assertRaises(OSError, self.bind)

    def test_mixed_previous_roots_rejected(self):
        self.bind()
        d = self.job / 'dependencies/build-vendor'
        d.mkdir()
        (d / 'debian-root.json').write_text(json.dumps({'reference_selection': {'operator_configuration_sha256': '0' * 64}}))
        self.assertRaises(ValueError, self.bind)

    def test_policy_and_prepare_use_capture_before_read(self):
        environ = dict(PEKIT_RECIPE_ROOT='/recipe/dev.peios.authd', PEKIT_COMMAND='build', PEKIT_TARGET='vendor', PEKIT_JOB_STATE=str(self.job), PEKIT_SANDBOX_ROOT=str(self.d / 'root'), PEKIT_DEBIAN_ROOT_STORE=str(self.d / 'store'), PEKIT_DEPENDENCIES='cargo *')
        policies = []

        def acquire(job, store, deps, policy, cached):
            policies.append((policy, r.configuration()['label']))
            cached.mkdir(parents=True)
            (cached / 'installed.tsv').write_text('fixture')
            return {'fixture': True}
        with patch.dict(os.environ, environ), patch.object(p, 'acquire', side_effect=acquire), patch.object(p, 'restore'):
            p.prepare()
            self.write_config('B')
            os.environ['PEKIT_TARGET'] = 'main'
            os.environ['PEKIT_DEPENDENCIES'] = 'cargo *\ngcc *'
            p.prepare()
        self.assertEqual(policies[0], policies[1])
        self.assertEqual(policies[0][1], 'A')

    def test_separate_processes_share_capture(self):
        script = "import sys,fcntl,json; from pathlib import Path\nsys.dont_write_bytecode=True\nsys.path.insert(0,sys.argv[1]);import reference as r\nr.CONFIG=Path(sys.argv[2]);job=Path(sys.argv[3])\nwith (job/'debian.lock').open('a') as f:\n fcntl.flock(f,fcntl.LOCK_EX);r.bind_job_configuration(job,'dev.peios.authd')\n print(r.configuration_digest())\n"
        cmd = [sys.executable, '-c', script, str(D), str(r.CONFIG), str(self.job)]
        a = subprocess.check_output(cmd, text=True).strip()
        self.write_config('B')
        b = subprocess.check_output(cmd, text=True).strip()
        self.assertEqual(a, b)

    def test_non_rust_needs_no_selection(self):
        r.CONFIG.unlink()
        r.bind_job_configuration(self.job, 'dev.peios.loregd')
        self.assertFalse((self.job / 'dependencies/reference-selection.json').exists())
if __name__ == '__main__':
    unittest.main(verbosity=2)
