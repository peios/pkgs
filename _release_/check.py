#!/usr/bin/env python3
"""Execute a required, committed release acceptance command; never infer success."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


def main(argv):
    if len(argv) != 2 or argv[1] not in {
        "source-reconstruction", "reproducibility", "integration"
    }:
        raise ValueError("expected source-reconstruction, reproducibility or integration")
    release = Path(os.environ["PEKIT_RELEASE_DIR"])
    repository = Path(os.environ["PEKIT_RELEASE_REPOSITORY"])
    candidate = json.loads((release / "candidate.json").read_text())
    if candidate.get("schema") != 1 or not candidate.get("artifacts"):
        raise ValueError("missing candidate selection")
    if not (repository / "index/active.json").is_file():
        raise ValueError("candidate repository has not been assembled")
    policy = tomllib.loads(Path(__file__).with_name("commands.toml").read_text())
    command = policy.get("checks", {}).get(argv[1])
    if not isinstance(command, list) or not command or not all(
        isinstance(word, str) and word for word in command
    ):
        raise ValueError(
            f"{argv[1]} is not configured in _release_/commands.toml; "
            "finish and wire the actual acceptance test before public promotion"
        )
    # No shell interpolation and no reused success record. The command executes
    # for this exact candidate; its output and failure are retained by Pekit.
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (OSError, KeyError, ValueError) as error:
        print(f"release acceptance: {error}", file=sys.stderr)
        sys.exit(1)
