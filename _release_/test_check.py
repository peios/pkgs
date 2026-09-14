import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("check.py"))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class AcceptanceTests(unittest.TestCase):
    def test_required_runner_executes_and_failure_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index").mkdir()
            (root / "index/active.json").write_text("{}")
            (root / "candidate.json").write_text(json.dumps({"schema": 1, "artifacts": ["fixture"]}))
            with patch.dict(os.environ, PEKIT_RELEASE_DIR=directory, PEKIT_RELEASE_REPOSITORY=directory), patch.object(CHECK, "__file__", str(root / "check.py")):
                (root / "commands.toml").write_text("[checks]\n")
                with self.assertRaisesRegex(ValueError, "not configured"):
                    CHECK.main(["check.py", "integration"])
                (root / "commands.toml").write_text("[checks]\nintegration=['sh','-c','exit 7']\n")
                self.assertEqual(CHECK.main(["check.py", "integration"]), 7)
                (root / "commands.toml").write_text("[checks]\nintegration=['sh','-c','test -f \"$PEKIT_RELEASE_DIR/candidate.json\"']\n")
                self.assertEqual(CHECK.main(["check.py", "integration"]), 0)
                (root / "candidate.json").write_text('{}')
                with self.assertRaisesRegex(ValueError, "missing candidate"):
                    CHECK.main(["check.py", "integration"])


if __name__ == "__main__":
    unittest.main()
