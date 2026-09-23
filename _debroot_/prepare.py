#!/usr/bin/env python3
"""Coordinator-only Debian root acquisition and verified, network-free replay."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import sys
sys.dont_write_bytecode = True
import reference

IMAGE = "debian:trixie"
# Coordinator-owned reference exceptions. Native publication policy is unchanged.
# These rolling upstreams require dependencies newer than Debian stable.
REFERENCE_IMAGES = {
    "org.gnome.libxslt": "debian:sid",
    "org.golang.go": "debian:sid",
    "org.rust-lang.rust": "debian:sid",
    # Go modules that require a newer Go than Debian stable ships.
    "dev.peios.loregd": "debian:sid",
    "dev.peios.peipkg": "debian:sid",
}

def selected_image():
    recipe = Path(os.environ.get("PEKIT_RECIPE_ROOT", "")).name
    return REFERENCE_IMAGES.get(recipe, IMAGE)

SCHEMA = 1
OPS = {"=": "eq", ">=": "ge", ">": "gt", "<=": "le", "<": "lt"}


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def requests(text):
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        name = parts[0]
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+(?::[a-z0-9][a-z0-9-]*)?", name):
            raise ValueError(f"invalid concrete apt package name: {name}")
        constraint = parts[1].strip() if len(parts) == 2 else "*"
        checks = result.setdefault(name, set())
        if constraint == "*":
            continue
        for clause in constraint.split(","):
            match = re.fullmatch(r"\s*(>=|<=|=|>|<)\s*([0-9][A-Za-z0-9.+:~\-]*)\s*", clause)
            if not match:
                raise ValueError(f"unsupported apt constraint for {name}: {constraint}")
            checks.add(match.groups())
    return [{"name": name, "checks": [list(c) for c in sorted(checks)]}
            for name, checks in sorted(result.items())]


def install_script(deps):
    # One APT solver transaction, followed by assertions over the FINAL state.
    selections = []
    names = []
    assertions = []
    for dep in deps:
        name = dep["name"]
        checks = dep["checks"]
        names.append(name)
        if checks:
            # APT's normal solver only considers its policy candidate. Exclude
            # disallowed versions BEFORE choosing candidates, including versions
            # already installed by the base image. Priority 1001 permits a
            # constraint-required downgrade in this disposable root.
            selections.extend([
                f'name={shlex.quote(name)}',
                "versions=$({ apt-cache madison \"$name\" | awk '{print $3}'; "
                "dpkg-query -W -f='${Version}\\n' \"$name\" 2>/dev/null || :; } | sort -u)",
                'for version in $versions; do',
                '  priority=1001',
            ])
            for op, version in checks:
                selections.append(f'  dpkg --compare-versions "$version" {OPS[op]} '
                                  f'{shlex.quote(version)} || priority=-1')
            selections.extend([
                "  printf 'Package: %s\\nPin: version %s\\nPin-Priority: %s\\n\\n' "
                '"$name" "$version" "$priority" >> /etc/apt/preferences.d/pekit-constraints',
                'done',
            ])
        assertions.extend([
            f'name={shlex.quote(name)}',
            'test "$(dpkg-query -W -f=\'${db:Status-Status}\' "$name")" = installed',
            'actual=$(dpkg-query -W -f=\'${Version}\' "$name")',
        ])
        for op, version in checks:
            assertions.append(
                f'dpkg --compare-versions "$actual" {OPS[op]} {shlex.quote(version)} || '
                f'{{ echo "unsatisfied dependency: $name $actual ({op} {version})" >&2; exit 1; }}')
    solver = ""
    if names:
        solver = ("apt-get install -y -q --no-install-recommends --allow-downgrades "
                  + shlex.join(names) + "\n")
    return """set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -q -o APT::Update::Error-Mode=any
""" + "\n".join(selections) + "\n" + solver + "\n".join(assertions) + """
# Record all installed packages including architecture and dpkg state.
dpkg-query -W -f='${binary:Package}\\t${Version}\\t${Architecture}\\t${db:Status-Status}\\n' > /tmp/dependencies.unsorted
LC_ALL=C sort /tmp/dependencies.unsorted > /tmp/dependencies.tsv
rm /tmp/dependencies.unsorted
apt-get indextargets > /tmp/apt-index-targets.txt
apt-get clean
# Workers use uid/gid 1000. The base must not silently assign it another identity.
if getent passwd 1000 || getent group 1000; then
  echo "base image reserves worker uid/gid 1000" >&2; exit 1
fi
printf 'peibuild:x:1000:1000:Package builder:/tmp:/bin/sh\\n' >> /etc/passwd
printf 'peibuild:x:1000:\\n' >> /etc/group
"""


def policy_id():
    # reference.py carries every pinned prerequisite, so its bytes are part of
    # the policy; the repository snapshot a job composes from is recorded in
    # each root's reference evidence.
    root = Path(__file__).resolve().parent
    return hashlib.sha256((digest(root / 'enter.sh') + digest(root / 'prepare.py') +
                           digest(root / 'reference.py') + selected_image()).encode()).hexdigest()


def load_record(directory, deps, policy):
    manifest = json.loads((directory / "debian-root.json").read_text())
    if (manifest.get("schema") != SCHEMA or manifest.get("requests") != deps
            or manifest.get("policy_sha256") != policy
            or manifest.get("host_architecture") != platform.machine()):
        raise ValueError(f"incompatible Debian replay/cache record: {directory}")
    for key in ("root_sha256", "installed_sha256"):
        if not re.fullmatch("[a-f0-9]{64}", manifest.get(key, "")):
            raise ValueError(f"invalid {key} in {directory}")
    if digest(directory / "installed.tsv") != manifest["installed_sha256"]:
        raise ValueError(f"corrupt installed-package record: {directory}")
    if 'reference_sha256' in manifest:
        if digest(directory / 'reference-prerequisites.json') != manifest['reference_sha256']:
            raise ValueError('corrupt reference prerequisite record')
    return manifest


def restore(store, manifest, destination):
    archive = store / (manifest["root_sha256"] + ".tar.gz")
    # Verify the SAME open archive that tar consumes; replacement of the path
    # between verification and extraction must not change the bytes used.
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["root_sha256"]:
            raise ValueError(f"corrupt Debian root archive: {archive}")
        stream.seek(0)
        destination.mkdir(parents=True, exist_ok=False)
        try:
            subprocess.run(["tar", "--no-same-owner", "-xzf", "-", "-C", str(destination)],
                           stdin=stream, check=True)
            if digest(destination / "tmp/dependencies.tsv") != manifest["installed_sha256"]:
                raise ValueError("root archive does not match installed-package record")
            if 'reference_sha256' in manifest:
                if digest(destination / 'usr/share/pekit-reference/reference-prerequisites.json') != manifest['reference_sha256']:
                    raise ValueError('root archive does not match reference record')
        except BaseException:
            shutil.rmtree(destination)
            raise


def catalogue_index(deps):
    """Names the signed repository defines, read only when a request names a
    reverse-DNS catalogue package."""
    if not any(reference.is_catalogue_name(dep["name"]) for dep in deps):
        return set()
    snapshot, _ = reference.repository()
    return reference.index_names(snapshot)


def acquire(job, store, deps, policy, output):
    target = os.environ["PEKIT_COMMAND"] + "-" + os.environ["PEKIT_TARGET"]
    names = catalogue_index(deps)
    selected = reference.selection(Path(os.environ["PEKIT_RECIPE_ROOT"]).name, target, deps, names)
    effective = reference.effective_requests(deps, selected, names)
    base_path = job / "debian-base.json"
    if base_path.exists():
        base = json.loads(base_path.read_text())
        if base.get("policy_sha256") != policy:
            raise ValueError("Debian preparation policy changed during retained job; rebuild")
    else:
        image = selected_image()
        run("docker", "pull", image)
        info = json.loads(run("docker", "image", "inspect", image, capture=True))[0]
        base = {"image": image, "image_id": info["Id"], "repo_digests": info["RepoDigests"],
                "architecture": info["Architecture"], "os": info["Os"], "policy_sha256": policy}
        atomic(base_path, encoded(base))
    # Never execute the mutable tag after resolving it for this job. Overlay
    # preparation needs a running container after APT finishes; ordinary roots
    # retain the existing start-and-wait lifecycle.
    overlay = selected is not None
    command = ['sleep', 'infinity'] if overlay else ['sh', '-euc', install_script(effective)]
    container = run('docker', 'create', '--network', 'bridge', base['image_id'],
                    *command, capture=True).strip()
    try:
        if overlay:
            run('docker', 'start', container)
            run('docker', 'exec', container, 'sh', '-euc', install_script(effective))
        else:
            run('docker', 'start', '-a', container)
            if run('docker', 'inspect', '-f', '{{.State.ExitCode}}', container, capture=True).strip() != '0':
                raise ValueError('Debian dependency installation failed')
        with tempfile.TemporaryDirectory(prefix=".acquire-", dir=store) as temp:
            temp = Path(temp)
            ref_record = None
            if overlay:
                ref_record = reference.install_container(container, selected, temp / 'reference-sdk',
                                                         store / 'upstream')
            installed = temp / "installed.tsv"
            run("docker", "cp", f"{container}:/tmp/dependencies.tsv", str(installed))
            raw = temp / "root.tar"
            run("docker", "export", container, "-o", str(raw))
            archive = temp / "root.tar.gz"
            with archive.open("wb") as stream:
                subprocess.run(["gzip", "-1", "-n", "-c", str(raw)], stdout=stream, check=True)
                stream.flush()
                os.fsync(stream.fileno())
            root_hash = digest(archive)
            manifest = {"schema": SCHEMA, "requests": deps, "policy_sha256": policy,
                        "host_architecture": platform.machine(), "base": base,
                        "root_sha256": root_hash, "root_bytes": archive.stat().st_size,
                        "installed_sha256": digest(installed)}
            if selected is not None:
                manifest['effective_apt_requests'] = effective
                manifest['reference_selection'] = selected
            if ref_record is not None:
                ref_bytes = reference.encoded(ref_record)
                manifest['reference_sha256'] = hashlib.sha256(ref_bytes).hexdigest()
                atomic(output / 'reference-prerequisites.json', ref_bytes)
            # Published archives are immutable. An existing corrupt object is an
            # error, never an excuse to silently change a historic environment.
            destination = store / (root_hash + ".tar.gz")
            try:
                os.link(archive, destination)
                sync_directory(store)
            except FileExistsError:
                if digest(destination) != root_hash:
                    raise ValueError(f"corrupt existing archive: {destination}")
            atomic(output / "installed.tsv", installed.read_bytes())
            atomic(output / "debian-root.json", encoded(manifest))  # completion marker last
            return manifest
    finally:
        run("docker", "rm", "-f", container)


def prepare():
    deps = requests(os.environ.get("PEKIT_DEPENDENCIES", ""))
    job = Path(os.environ["PEKIT_JOB_STATE"]).resolve()
    destination = Path(os.environ["PEKIT_SANDBOX_ROOT"]).absolute()
    target = os.environ["PEKIT_COMMAND"] + "-" + os.environ["PEKIT_TARGET"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", target):
        raise ValueError("invalid Debian environment record target")
    default_store = Path((os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state"))) / "pekit/debian-roots"
    store = Path((os.environ.get("PEKIT_DEBIAN_ROOT_STORE") or str(default_store))).resolve()
    replay = os.environ.get("PEKIT_DEBIAN_REPLAY")
    job.mkdir(parents=True, exist_ok=True)
    # Serialize preparation within one job; unrelated jobs can acquire in parallel.
    with (job / "debian.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        policy = policy_id()
        key = hashlib.sha256(encoded({"requests": deps, "policy": policy})).hexdigest()
        cached = Path(replay).resolve() / target if replay else job / "debian-roots" / key
        if replay or (cached / "debian-root.json").exists():
            manifest = load_record(cached, deps, policy)
        else:
            store.mkdir(parents=True, exist_ok=True)
            manifest = acquire(job, store, deps, policy, cached)
        restore(store, manifest, destination)
        record = job / "dependencies" / target
        atomic(record / "installed.tsv", (cached / "installed.tsv").read_bytes())
        if 'reference_sha256' in manifest:
            atomic(record / 'reference-prerequisites.json', (cached / 'reference-prerequisites.json').read_bytes())
        atomic(record / "debian-root.json", encoded(manifest))


if __name__ == "__main__":
    try:
        prepare()
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Debian root preparation failed: {error}")
