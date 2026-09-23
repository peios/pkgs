import importlib.machinery
import importlib.util
import json
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("crl", str(HERE.parent / "collect-rust-licences"))
spec = importlib.util.spec_from_loader(loader.name, loader)
crl = importlib.util.module_from_spec(spec)
loader.exec_module(crl)


def package(root, name, version, licence, source, deps=()):
    crate = root / f"{name}-{version}"
    crate.mkdir(parents=True, exist_ok=True)
    (crate / "Cargo.toml").write_text("")
    return {"id": f"{name} {version}", "name": name, "version": version, "license": licence,
            "source": source, "manifest_path": str(crate / "Cargo.toml")}, list(deps)


def metadata(entries):
    packages, nodes = [], []
    for pkg, deps in entries:
        packages.append(pkg)
        nodes.append({"id": pkg["id"], "deps": [
            {"pkg": d, "dep_kinds": [{"kind": kind}]} for d, kind in deps]})
    return {"packages": packages, "resolve": {"nodes": nodes}}


class Collect(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.vendor = self.tmp / "vendor"
        self.out = self.tmp / "licences"

    def test_closure_notices_and_expression(self):
        registry = "registry+https://github.com/rust-lang/crates.io-index"
        app = package(self.vendor, "app", "1.0.0", "MIT", None,
                      [("serde 1.0.0", None), ("cc 1.0.0", "build"), ("proptest 1.0.0", "dev")])
        serde = package(self.vendor, "serde", "1.0.0", "MIT/Apache-2.0", registry)
        cc = package(self.vendor, "cc", "1.0.0", "Apache-2.0", registry)
        proptest = package(self.vendor, "proptest", "1.0.0", "GPL-3.0-only", registry)
        for crate in ("serde-1.0.0", "cc-1.0.0", "proptest-1.0.0"):
            (self.vendor / crate / "LICENSE-MIT").write_text("notice")
        data = metadata([app, serde, cc, proptest])
        expression = crl.collect(data, {"app"}, self.out, {})
        # Dev-dependencies never ship; the legacy slash form means OR.
        self.assertEqual(expression, "Apache-2.0 AND (Apache-2.0 OR MIT) AND MIT")
        self.assertTrue((self.out / "serde-1.0.0" / "LICENSE-MIT").is_file())
        self.assertTrue((self.out / "cc-1.0.0").is_dir())
        self.assertFalse((self.out / "proptest-1.0.0").exists())
        self.assertFalse((self.out / "app-1.0.0").exists())
        self.assertIn("serde\t1.0.0\tApache-2.0 OR MIT\t", (self.out / "crate-licenses.tsv").read_text())

    def test_missing_notice_fails_unless_supplied(self):
        git = "git+https://github.com/peios/peios-rs.git#abc"
        app = package(self.vendor, "app", "1.0.0", "MIT", None, [("peios 0.1.0", None)])
        peios = package(self.vendor, "peios", "0.1.0", "MIT", git)
        data = metadata([app, peios])
        with self.assertRaises(SystemExit):
            crl.collect(data, {"app"}, self.out, {})
        notice = self.tmp / "peios-rs-LICENSE"
        notice.write_text("MIT")
        crl.collect(data, {"app"}, self.out, {"git+https://github.com/peios/peios-rs.git": notice})
        self.assertTrue((self.out / "peios-0.1.0" / "peios-rs-LICENSE").is_file())

    def test_exact_crate_notice_beats_source_prefix(self):
        registry = "registry+https://github.com/rust-lang/crates.io-index"
        app = package(self.vendor, "app", "1.0.0", "MIT", None, [("vsimd 0.8.0", None)])
        vsimd = package(self.vendor, "vsimd", "0.8.0", "MIT", registry)
        data = metadata([app, vsimd])
        notice = self.tmp / "vsimd-LICENSE"
        notice.write_text("MIT")
        crl.collect(data, {"app"}, self.out, {"vsimd@0.8.0": notice})
        self.assertTrue((self.out / "vsimd-0.8.0" / "vsimd-LICENSE").is_file())

    def test_check_rejects_a_stale_declared_licence(self):
        app = package(self.vendor, "app", "1.0.0", "MIT", None)
        meta = self.tmp / "meta.json"
        meta.write_text(json.dumps(metadata([app])))
        good = self.tmp / "good.toml"
        good.write_text('[package]\nlicense = "MIT"\n')
        crl.main(["--licence-root", str(self.out), "--root", "app", "--metadata-json", str(meta),
                  "--check", str(good)])
        stale = self.tmp / "stale.toml"
        stale.write_text('[package]\nlicense = "Apache-2.0"\n')
        with self.assertRaises(SystemExit):
            crl.main(["--licence-root", str(self.out), "--root", "app", "--metadata-json", str(meta),
                      "--check", str(stale)])

    def test_unknown_root_fails(self):
        app = package(self.vendor, "app", "1.0.0", "MIT", None)
        with self.assertRaises(SystemExit):
            crl.collect(metadata([app]), {"nope"}, self.out, {})


if __name__ == "__main__":
    unittest.main()
