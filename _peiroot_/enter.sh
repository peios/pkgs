#!/bin/sh
# Sandbox command of the workspace's default profile (env.pekit.toml). Every
# target gets a native root composed from its declared peipkg set by
# compose-root.sh.
#
# build:vendor is the only networked target. It acquires sources in a clean
# native root built from the vendor target's declared peipkg set. Peios glibc
# resolves hosts only through resolvd's socket, which no sandbox runs, so the
# root also gets resolvd's NSS shim and the build-root resolver
# (buildroot-resolver.py), started by entry.sh for this job only. TLS
# trust comes from the declared Mozilla bundle, which trustd composes on a
# booted system but nothing composes in a build root. Go needs neither shim
# nor resolver (its netgo resolver reads the copied resolv.conf), but receives
# them like every other acquisition.
#
# Compilation and tests always run offline in the native root. The host root,
# home, rustup, cargo credentials and caches are never mounted.
set -eu
entry() {
  mkdir -p "$PEKIT_SANDBOX_ROOT/usr/libexec/peiroot"
  install -m 0755 "$PEKIT_WORKSPACE_ROOT/_peiroot_/entry.sh" \
    "$PEKIT_SANDBOX_ROOT/usr/libexec/peiroot/entry"
}

if [ "${PEKIT_COMMAND:-}:${PEKIT_TARGET:-}" = build:vendor ]; then
  PEKIT_DEPENDENCIES=$(python3 - "$PEKIT_DEPENDENCIES_FILE" <<'PYDEPS'
import json, sys
with open(sys.argv[1]) as f:
    deps = dict(json.load(f)["all_providers"].get("peipkg", {}))
if not deps:
    sys.exit("vendor acquisition requires declared peipkg dependencies")
# Only what the acquisition machinery itself needs: a shell for the entry,
# python3 for the resolver, and resolvd's NSS shim for it to answer through.
# Recipes declare every tool their commands use, as in any native root;
# nothing else is ambient. Recipe constraints always take precedence.
for name in ["org.git.kernel.dash", "org.mozilla.ca-certificates",
             "org.python.python3", "dev.peios.resolvd-nss"]:
    deps.setdefault(name, "*")
for name, constraint in sorted(deps.items()):
    print(name, constraint)
PYDEPS
  )
  export PEKIT_DEPENDENCIES
  "$PEKIT_WORKSPACE_ROOT/_peiroot_/compose-root.sh"
  # The two bundle paths trustd renders on a booted system: Go's first probe,
  # and OpenSSL's default CAfile (libcurl, hence git and Cargo, read it).
  bundle="$PEKIT_SANDBOX_ROOT/usr/share/ca-certificates/mozilla.crt"
  for trust in etc/ssl/certs/ca-certificates.crt etc/ssl/cert.pem; do
    trust="$PEKIT_SANDBOX_ROOT/$trust"
    [ -e "$trust" ] && continue
    [ -s "$bundle" ] || {
      echo "peiroot: native acquisition root has no Mozilla trust bundle" >&2
      exit 1
    }
    mkdir -p "${trust%/*}"
    cp "$bundle" "$trust"
  done
  entry
  install -m 0644 "$PEKIT_WORKSPACE_ROOT/_peiroot_/buildroot-resolver.py" \
    "$PEKIT_SANDBOX_ROOT/usr/libexec/peiroot/buildroot-resolver.py"
  exit 0
fi
"$PEKIT_WORKSPACE_ROOT/_peiroot_/compose-root.sh"
entry
