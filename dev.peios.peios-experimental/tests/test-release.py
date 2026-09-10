#!/usr/bin/env python3
"""Validate the edition identity and policy data staged by the recipe."""

from pathlib import Path
import os
import shlex
import tomllib


root = Path(os.environ["PEKIT_OUT"])
os_release = root / "usr/lib/os-release"
compat = root / "usr/etc/os-release"
release_toml = root / "usr/share/peios/release.toml"

assert os_release.is_file()
assert compat.is_symlink()
assert os.readlink(compat) == "../lib/os-release"

identity = {}
for raw_line in os_release.read_text(encoding="utf-8").splitlines():
    key, value = raw_line.split("=", 1)
    parsed = shlex.split(value)
    assert len(parsed) == 1
    identity[key] = parsed[0]

version = os.environ["PEKIT_VERSION"]
assert identity == {
    "NAME": "Peios",
    "ID": "peios",
    "VERSION_ID": version,
    "VERSION": f"{version} (Experimental)",
    "VARIANT": "Experimental",
    "VARIANT_ID": "experimental",
    "PRETTY_NAME": f"Peios {version} Experimental",
    "DOCUMENTATION_URL": "https://learn.peios.org/",
}

with release_toml.open("rb") as stream:
    release = tomllib.load(stream)

assert set(release) == {"registry"}
registry = release["registry"]
assert set(registry) == {"autoapply", "live_autoapply", "install_autoapply"}
assert registry["autoapply"] == [
    "port-reservations",
    "pnp-rules",
    "eudev-service",
    "authd-service",
    "authd-policy",
    "lpsd-service",
    "lpsd-authd-registration",
    "login-console",
    "eventd-config",
    "eventd-service",
    "netd-service",
    "netd-default-profile",
    "resolvd-service",
    "resolvd-port",
    "trustd-service",
    "timed-service",
    "timed-policy",
    "atriumd-service",
    "pnpd-service",
    "installerd-service",
]
assert registry["live_autoapply"] == ["lpsd-first-account"]
assert registry["install_autoapply"] == ["oobe-service"]
