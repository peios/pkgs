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
recipe_toml = Path("package.pekit.toml")

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

# The edition is the release manifest, not merely the three files above. Keep
# the first-party identity transition and cross-root edges under test as well:
# a valid payload with a stale alias would otherwise package successfully and
# defer the failure until image resolution.
with recipe_toml.open("rb") as stream:
    recipe = tomllib.load(stream)

assert recipe["package"]["name"] == "dev.peios.peios-experimental"
assert recipe["package"]["architecture"] == "x86_64"
assert recipe["package"]["version"] == "{{version}}-15"
assert recipe["provides"]["peios-release"] == "{{version}}"
assert recipe["provides"]["peios-experimental"] == "{{version}}-15"
assert recipe["replaces"] == {"peios-experimental": "<= 2026.8-11"}
assert recipe["conflicts"] == {"peios-experimental": "*"}

dependencies = recipe["dependencies"]
expected_first_party = {
    "dev.peios.atrium": ">= 0.0.25-2",
    "dev.peios.authd": ">= 0.0.14-1",
    "dev.peios.authd-live-account": ">= 0.0.14-1",
    "dev.peios.authd-login": ">= 0.0.14-1",
    "dev.peios.authd-lps": ">= 0.0.14-1",
    "dev.peios.authd-lpsd": ">= 0.0.14-1",
    "dev.peios.authd-nss": ">= 0.0.14-1",
    "dev.peios.clock": ">= 0.1.1-1",
    "dev.peios.eventd": ">= 0.1.0-10",
    "dev.peios.libpeios": ">= 0.5.0-1",
    "dev.peios.net": ">= 0.1.1-15",
    "dev.peios.netd": ">= 0.1.1-15",
    "dev.peios.oobe": ">= 0.1.1-18",
    "dev.peios.peinit": ">= 0.0.2-1",
    "dev.peios.peios-install": ">= 0.3.0-8",
    "dev.peios.peios-installer": ">= 0.1.1-18",
    "dev.peios.peiosutils": ">= 0.8.6-1",
    "dev.peios.peipkg": ">= 0.1.3-1",
    "dev.peios.pnpd": ">= 0.5.1-2",
    "dev.peios.resolv": ">= 0.1.0-7",
    "dev.peios.resolvd": ">= 0.1.0-7",
    "dev.peios.resolvd-nss": ">= 0.1.0-7",
    "dev.peios.timed": ">= 0.1.1-1",
    "dev.peios.trust": ">= 0.1.1-1",
    "dev.peios.trustd": ">= 0.1.1-1",
}
for name, floor in expected_first_party.items():
    assert dependencies[name] == floor

expected_initramfs = {
    "dev.peios.coldplug-irf": ">= 1.0.0-3",
    "dev.peios.fsbase-irf": ">= 1.0.0-10",
    "dev.peios.fsbase-stratafs-mount-hooks": ">= 1.0.0-10",
    "dev.peios.kernel-modules-irf": ">= 0.20.1-rc13-2",
    "dev.peios.prelude": ">= 0.0.3-1",
}
actual_initramfs = {
    name: edge["constraint"]
    for name, edge in dependencies.items()
    if isinstance(edge, dict) and edge.get("root") == "initramfs"
}
assert actual_initramfs == expected_initramfs

historical_first_party_names = {
    "clock",
    "net",
    "netd",
    "nss-peios-net",
    "peipkg",
    "peinit",
    "pnpd",
    "prelude",
    "resolv",
    "resolvd",
    "timed",
    "trust",
    "trustd",
}
assert historical_first_party_names.isdisjoint(dependencies)
