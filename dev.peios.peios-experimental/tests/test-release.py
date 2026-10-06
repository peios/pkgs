#!/usr/bin/env python3
"""Validate the edition identity and policy data staged by the recipe."""

from pathlib import Path
import os
import re
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
    "event-policy",
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
    "console-keymap",
    "sshd-service",
    "sshd-network",
    "gxwid-service",
    "gxwi-config",
    "gxwi-network",
    "fenestra-config",
    "fenesh-config",
    "security-descriptor-builder",
    "pnpd-service",
    "installerd-service",
]
assert registry["live_autoapply"] == ["lpsd-first-account", "installer-gxwi-overlay"]
assert registry["install_autoapply"] == ["oobe-service"]

# The edition is the release manifest, not merely the three files above. Keep
# the first-party identity transition and cross-root edges under test as well:
# a valid payload with a stale alias would otherwise package successfully and
# defer the failure until image resolution.
with recipe_toml.open("rb") as stream:
    recipe = tomllib.load(stream)

assert recipe["package"]["name"] == "dev.peios.peios-experimental"
# The edition ships portable release/policy data; dependencies resolve for
# the target architecture independently of this metadata package.
assert recipe["package"]["architecture"] == "noarch"
# The package version is the OS release plus any packaging revision.
assert re.fullmatch(re.escape(version) + r"-[1-9][0-9]*", recipe["package"]["version"]), recipe["package"]["version"]
assert "provides" not in recipe
assert "replaces" not in recipe
assert "conflicts" not in recipe

dependencies = recipe["dependencies"]
expected_first_party = {
    "dev.peios.gxwi": ">= 0.0.3-1",
    "dev.peios.fenestra": ">= 0.0.3-1",
    "dev.peios.fenesh": ">= 0.0.3-1",
    "dev.peios.gexora": ">= 0.0.3-1",
    "dev.peios.gxwi-sd-editor": ">= 0.0.1-1",
    "dev.peios.gxwi-file-dialog": ">= 0.0.1-1",
    "dev.peios.gxwi-feature-manager": ">= 0.0.1-1",
    "dev.peios.gxwi-package-manager": ">= 0.0.1-1",
    "dev.peios.gxwi-upgrade-peios": ">= 0.0.1-1",
    "dev.peios.gxwi-principals-manager": ">= 0.0.1-1",
    "dev.peios.gxwi-my-settings": ">= 0.0.1-1",
    "dev.peios.gxwi-disk-manager": ">= 0.0.1-1",
    "dev.peios.gxwi-services-manager": ">= 0.0.1-1",
    "dev.peios.gxwi-task-manager": ">= 0.0.1-1",
    "dev.peios.installer-gxwi": ">= 0.0.1-1",
    "dev.peios.oobe-gxwi": ">= 0.0.1-1",
    "dev.peios.openssh": ">= 10.5.1.2-1",
    "dev.peios.openssh-settings": ">= 10.5.1.2-1",
    "dev.peios.authd": ">= 0.0.24-1",
    "dev.peios.authd-live-account": ">= 0.0.24-1",
    "dev.peios.authd-login": ">= 0.0.24-1",
    "dev.peios.authd-lps": ">= 0.0.24-1",
    "dev.peios.authd-lpsd": ">= 0.0.24-1",
    "dev.peios.authd-nss": ">= 0.0.24-1",
    "dev.peios.clock": ">= 0.1.10-1",
    "dev.peios.eventd": ">= 0.1.11-1",
    "dev.peios.kernel": ">= 0.21.0-alpha11-1",
    "dev.peios.kernel-modules": ">= 0.21.0-alpha11-1",
    "dev.peios.libpeios": ">= 0.5.8-1",
    "dev.peios.net": ">= 0.1.8-1",
    "dev.peios.netd": ">= 0.1.8-1",
    "dev.peios.oobe": ">= 0.1.11-1",
    "dev.peios.peinit": ">= 0.0.12-1",
    "dev.peios.peinit-svctl": ">= 0.0.12-1",
    "dev.peios.peios-install": ">= 0.3.0-1",
    "dev.peios.peios-installer": ">= 0.1.11-1",
    "dev.peios.peiosutils": ">= 0.8.17-1",
    "dev.peios.peipkg": ">= 0.1.9-1",
    "dev.peios.pnpd": ">= 0.6.1-1",
    "dev.peios.resolv": ">= 0.1.6-1",
    "dev.peios.resolvd": ">= 0.1.6-1",
    "dev.peios.resolvd-nss": ">= 0.1.6-1",
    "dev.peios.timed": ">= 0.1.10-1",
    "dev.peios.trust": ">= 0.1.6-1",
    "dev.peios.trustd": ">= 0.1.6-1",
}
for name, floor in expected_first_party.items():
    assert dependencies[name] == floor

expected_initramfs = {
    "dev.peios.coldplug-irf": ">= 1.0.0-1",
    "dev.peios.fsbase-irf": ">= 1.0.0-1",
    "dev.peios.fsbase-stratafs-mount-hooks": ">= 1.0.0-1",
    "dev.peios.kernel-modules-irf": ">= 0.21.0-alpha11-1",
    "dev.peios.prelude": ">= 0.0.7-1",
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

assert "dev.peios.atrium" not in dependencies

# Operator tools must be explicit system-root dependencies. ELF library edges
# cannot provide tar's external compressors or less's interactive command.
for name in (
    "org.gnu.grep", "org.gnu.sed", "org.gnu.tar", "org.gnu.gawk",
    "org.gnu.findutils", "org.gnu.diffutils", "org.gnu.gzip", "org.tukaani.xz",
    "com.facebook.zstd", "org.sourceware.bzip2", "com.darwinsys.file",
    "com.greenwoodsoftware.less", "net.sourceforge.infozip.zip",
    "net.sourceforge.infozip.unzip", "org.gnu.nano",
    "se.curl.curl", "io.github.iputils.iputils", "org.kernel.iproute2",
    "org.isc.bind-utils", "org.debian.netcat-openbsd",
    "org.samba.rsync", "org.openssl.openssl",
    "org.debian.whois", "net.es.iperf3",
    "org.dest-unreach.socat", "org.tcpdump.libpcap", "org.tcpdump.tcpdump",
    "nl.bitwizard.mtr", "net.sourceforge.traceroute", "org.nmap.nmap",
):
    assert isinstance(dependencies[name], str) and dependencies[name].startswith(">= "), name
