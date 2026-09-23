import base64
import csv
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HELPERS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPERS))
import python_paths
import wheel_checks
loader = importlib.machinery.SourceFileLoader('test_tools', str(HELPERS / 'test-tools'))
spec = importlib.util.spec_from_loader(loader.name, loader)
tools = importlib.util.module_from_spec(spec)
loader.exec_module(tools)
wheel_loader = importlib.machinery.SourceFileLoader('install_wheel', str(HELPERS / 'install-wheel'))
install_wheel = importlib.util.module_from_spec(importlib.util.spec_from_loader(wheel_loader.name, wheel_loader))
wheel_loader.exec_module(install_wheel)


class Paths(unittest.TestCase):
    def test_native_matches_running_minor(self):
        expected = f'/usr/lib/x86_64-linux-peios/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
        with patch.object(python_paths.sysconfig, 'get_path', return_value=expected):
            self.assertEqual(str(python_paths.staged_site('/stage')), '/stage'+expected)

    def test_wrong_native_and_unsafe_paths_fail(self):
        for path in ['/usr/lib/python3/dist-packages', 'relative', '/usr/../escape', '/usr/lib']:
            with self.subTest(path=path), patch.object(python_paths.sysconfig, 'get_path', return_value=path):
                with self.assertRaises(ValueError):python_paths.staged_site('/stage')


class Shebangs(unittest.TestCase):
    def test_python_shebangs_name_the_runtime_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pkg').mkdir()
            cases = {
                'pkg/env.py': (b'#!/usr/bin/env python3\nprint(1)\n', b'#!/bin/python3\nprint(1)\n'),
                'pkg/usr.py': (b'#!/usr/bin/python3\nprint(2)\n', b'#!/bin/python3\nprint(2)\n'),
                'pkg/plain.py': (b'print(3)\n', b'print(3)\n'),
                'pkg/shell.sh': (b'#!/bin/sh\necho 4\n', b'#!/bin/sh\necho 4\n'),
                'pkg/options.py': (b'#!/usr/bin/env python3 -u\n', b'#!/usr/bin/env python3 -u\n'),
            }
            for name, (data, _) in cases.items():
                (root / name).write_bytes(data)
            self.assertEqual(install_wheel.rewrite_python_shebangs(root), 2)
            for name, (_, want) in cases.items():
                with self.subTest(name=name):
                    self.assertEqual((root / name).read_bytes(), want)


class Wheels(unittest.TestCase):
    def make_wheel(self, root, corrupt=False, missing=False):
        files = {'fixture.py': b'ANSWER = 42\n', 'fixture-1.dist-info/WHEEL': b'Root-Is-Purelib: true\n'}
        output = io.StringIO();writer=csv.writer(output)
        for name, data in files.items():
            if missing and name=='fixture.py':continue
            sha=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            writer.writerow([name,'sha256='+sha,str(len(data))])
        writer.writerow(['fixture-1.dist-info/RECORD','',''])
        files['fixture-1.dist-info/RECORD']=output.getvalue().encode()
        if corrupt:files['fixture.py']=b'ANSWER = 0\n'
        path=root/'fixture-1-py3-none-any.whl'
        with zipfile.ZipFile(path,'w') as z:
            for n,d in files.items():z.writestr(n,d)
        return path

    def test_generated_wheel_installs_and_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);wheel=self.make_wheel(root)
            wheel_checks.install_and_import(wheel,root/'installed','fixture')

    def test_record_rejects_changed_and_unlisted_files(self):
        for kwargs in [{'corrupt':True},{'missing':True}]:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):wheel_checks.verify_wheel(self.make_wheel(Path(tmp),**kwargs))

    def test_portable_wheel_can_contain_vendored_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.make_wheel(Path(tmp))
            with zipfile.ZipFile(path,'a') as z:z.writestr('fixture/vendor/dep.dist-info/WHEEL','Root-Is-Purelib: true\n')
            tools.portable(path)
            with zipfile.ZipFile(path,'a') as z:z.writestr('../escape','bad')
            with self.assertRaises(ValueError):tools.portable(path)

    def test_modified_acquisition_never_executes_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'wheels').mkdir();wheel=self.make_wheel(root/'wheels')
            req=root/'requirements.txt';req.write_text('fixture\n')
            manifest={'schema':1,'requirements_sha256':tools.sha(req),'files':{wheel.name:tools.sha(wheel)}}
            (root/'test-tools.json').write_text(json.dumps(manifest))
            wheel.write_bytes(b'changed')
            with patch.object(tools.subprocess,'run',side_effect=AssertionError('installer ran')):
                with self.assertRaisesRegex(ValueError,'changed'):tools.install(root,root/'env')

if __name__=='__main__':unittest.main()
