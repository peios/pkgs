#!/usr/bin/env python3
"""Keep the one-shot legacy migration trampoline exact and inert."""

from pathlib import Path
import tomllib


with Path("peios-experimental.package.pekit.toml").open("rb") as stream:
    recipe = tomllib.load(stream)

assert recipe["package"] == {
    "name": "peios-experimental",
    "version": "{{version}}-10",
    "architecture": "noarch",
    "description": "One-time migration from the legacy Experimental edition package name",
    "license": "MIT",
    "license_class": "free",
    "homepage": "https://github.com/peios/pkgs",
    "alternate_upgrade": {
        "message": "To upgrade Peios use the `upgrade-peios` command."
    },
}
assert recipe["dependencies"] == {
    "dev.peios.peios-experimental": ">= 2026.8-14"
}
assert "provides" not in recipe
assert "replaces" not in recipe
assert "conflicts" not in recipe
assert set(recipe["files"].values()) == {
    "usr/share/doc/peios-experimental/MIGRATION",
    "usr/share/licenses/peios-experimental/LICENSE",
}
