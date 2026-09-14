import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prepare", Path(__file__).with_name("prepare.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreparationTests(unittest.TestCase):
    def test_canonical_requests(self):
        self.assertEqual(p.requests("libc6 >=2:1.2~rc1, < 3\nlibc6 >= 2:1.2~rc1\nzlib1g:amd64 *"),
                         p.requests("zlib1g:amd64\nlibc6 <3,>=2:1.2~rc1"))

    def test_reject_unsupported_or_injected_requests(self):
        for value in ("--evil *", "foo >=1 || <2", "foo ^1.0", "foo 1.0", "foo >=1,", "foo =1;touch /tmp/a", "foo *\n$(id) *"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.requests(value)

    def make_record(self, root):
        deps = p.requests("libc6 >= 1")
        record = root / "records/build-main"
        record.mkdir(parents=True)
        installed = b"libc6\t2.0\tamd64\tinstalled\n"
        (record / "installed.tsv").write_bytes(installed)
        archive = root / "archive.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo("tmp/dependencies.tsv")
            info.size = len(installed)
            tar.addfile(info, io.BytesIO(installed))
        sha = p.digest(archive)
        store = root / "store"
        store.mkdir()
        archive.rename(store / (sha + ".tar.gz"))
        manifest = {"schema": 1, "requests": deps, "policy_sha256": p.policy_id(),
                    "host_architecture": platform.machine(), "root_sha256": sha,
                    "installed_sha256": p.digest(record / "installed.tsv")}
        p.atomic(record / "debian-root.json", p.encoded(manifest))
        return deps, record, store, manifest

    def test_offline_replay_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deps, record, store, manifest = self.make_record(root)
            env = {"PEKIT_DEPENDENCIES": "libc6 >=1", "PEKIT_JOB_STATE": str(root / "job"),
                   "PEKIT_SANDBOX_ROOT": str(root / "restored"), "PEKIT_COMMAND": "build",
                   "PEKIT_TARGET": "main", "PEKIT_DEBIAN_ROOT_STORE": str(store),
                   "PEKIT_DEBIAN_REPLAY": str(record.parent)}
            # The coordinator command runner (Docker/acquisition) is forbidden.
            with patch.dict(os.environ, env), patch.object(p, "run", side_effect=AssertionError("acquisition during replay")):
                p.prepare()
            self.assertEqual((root / "restored/tmp/dependencies.tsv").read_bytes(), (record / "installed.tsv").read_bytes())
            self.assertTrue((root / "job/dependencies/build-main/debian-root.json").is_file())
            (store / (manifest["root_sha256"] + ".tar.gz")).write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "corrupt Debian root"):
                p.restore(store, manifest, root / "bad")
            self.assertFalse((root / "bad").exists())

    def test_wrong_or_incomplete_record(self):
        with tempfile.TemporaryDirectory() as temp:
            deps, record, _, manifest = self.make_record(Path(temp))
            for key, value in (("schema", 99), ("requests", []), ("policy_sha256", "old"), ("host_architecture", "wrong"), ("root_sha256", "../../escape")):
                broken = dict(manifest, **{key: value})
                p.atomic(record / "debian-root.json", p.encoded(broken))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    p.load_record(record, deps, p.policy_id())
            p.atomic(record / "debian-root.json", p.encoded(manifest))
            (record / "installed.tsv").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "corrupt installed"):
                p.load_record(record, deps, p.policy_id())
            (record / "debian-root.json").unlink()
            with self.assertRaises(FileNotFoundError):
                p.load_record(record, deps, p.policy_id())

    def test_missing_archive_has_no_acquisition_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, record, store, manifest = self.make_record(root)
            (store / (manifest["root_sha256"] + ".tar.gz")).unlink()
            env = {"PEKIT_DEPENDENCIES": "libc6 >=1", "PEKIT_JOB_STATE": str(root / "job"),
                   "PEKIT_SANDBOX_ROOT": str(root / "restored"), "PEKIT_COMMAND": "build",
                   "PEKIT_TARGET": "main", "PEKIT_DEBIAN_ROOT_STORE": str(store),
                   "PEKIT_DEBIAN_REPLAY": str(record.parent)}
            with patch.dict(os.environ, env), patch.object(p, "acquire", side_effect=AssertionError("network fallback")):
                with self.assertRaises(FileNotFoundError):
                    p.prepare()
            self.assertFalse((root / "restored").exists())

    def test_one_immutable_base_even_after_failed_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = "sha256:" + "a" * 64
            calls = []
            def command(*args, **kwargs):
                calls.append(args)
                if args[:3] == ("docker", "image", "inspect"):
                    return json.dumps([{"Id": image, "RepoDigests": ["debian@" + image],
                                        "Architecture": "amd64", "Os": "linux"}])
                if args[:2] == ("docker", "create"):
                    self.assertEqual(args[4], image)
                    raise OSError("simulated create failure")
                return ""
            with patch.object(p, "run", side_effect=command):
                for deps in (p.requests("gcc *"), p.requests("libc6 *")):
                    with self.assertRaisesRegex(OSError, "simulated"):
                        p.acquire(root, root, deps, "policy", root / "record")
            self.assertEqual(sum(c[:2] == ("docker", "pull") for c in calls), 1)
            self.assertFalse((root / "record/debian-root.json").exists())
            with patch.object(p, "run", side_effect=AssertionError("policy drift acquisition")):
                with self.assertRaisesRegex(ValueError, "policy changed"):
                    p.acquire(root, root, [], "changed-policy", root / "record")

    def test_archive_inventory_mismatch_removes_partial_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, store, manifest = self.make_record(root)
            manifest["installed_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "does not match"):
                p.restore(store, manifest, root / "bad")
            self.assertFalse((root / "bad").exists())


@unittest.skipUnless(os.environ.get("PEKIT_TEST_DEBIAN") == "1", "requires Docker; opts into disposable local APT fixtures")
class AptIntegrationTests(unittest.TestCase):
    def check_solver(self, request, expected, preinstall="", fails=False):
        fixture = Path(__file__).with_name("solver-fixture.sh").read_text()
        script = p.install_script(p.requests(request))
        if preinstall:
            fixture += "dpkg -i /tmp/repo/pekit-fixture-beta-2.0.deb\n"
        command = "sh -euc " + shlex.quote(script)
        if fails:
            command = "if " + command + "; then exit 98; fi"
        fixture += command + "\n" + expected + "\n"
        proc = subprocess.run(["docker", "run", "--rm", "--network", "none", "-i", "debian:trixie", "sh", "-eu"],
                              input=fixture, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_non_candidate_upper_bound(self):
        self.check_solver("pekit-fixture-beta >=1.0, <2.0",
                          "test \"$(dpkg-query -W -f='${Version}' pekit-fixture-beta)\" = 1.0")

    def test_downgrade_installed_candidate(self):
        self.check_solver("pekit-fixture-beta =1.0",
                          "test \"$(dpkg-query -W -f='${Version}' pekit-fixture-beta)\" = 1.0", preinstall=True)

    def test_joint_conflict_fails_before_install(self):
        self.check_solver("pekit-fixture-beta <2.0\npekit-fixture-alpha *",
                          "! dpkg-query -W pekit-fixture-beta", fails=True)

    def test_joint_transitive_upgrade(self):
        self.check_solver("pekit-fixture-beta >=1.0\npekit-fixture-alpha *",
                          "test \"$(dpkg-query -W -f='${Version}' pekit-fixture-beta)\" = 2.0")

    def test_unsatisfiable_bound(self):
        self.check_solver("pekit-fixture-beta >2.0",
                          "! dpkg-query -W pekit-fixture-beta", fails=True)


if __name__ == "__main__":
    unittest.main()
