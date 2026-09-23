#!/bin/sh
# build:vendor is the only networked target. It acquires sources in a clean
# root chosen by the recipe's declared acquisition dependencies:
#
#   * Native, when the vendor target declares a non-empty peipkg set. Peios
#     glibc resolves hosts only through resolvd's socket, which no sandbox
#     runs, so the root also gets resolvd's NSS shim and the build-root
#     resolver (buildroot-resolver.py), started by net-entry.sh for this job
#     only. TLS trust comes from the declared Mozilla bundle, which trustd
#     composes on a booted system but nothing composes in a build root. Go
#     needs neither shim nor resolver (its netgo resolver reads the copied
#     resolv.conf), but receives them like every other native acquisition.
#   * Debian, for vendor targets whose native set is still empty: acquisition
#     tools not yet packaged natively (pip, gnupg for the Rust stage0
#     signature) keep their declared apt set until they are.
#
# Compilation and tests always run offline in the native root. The host root,
# home, rustup, cargo credentials and caches are never mounted.
set -eu
entry() {
  mkdir -p "$PEKIT_SANDBOX_ROOT/usr/libexec/peiroot"
  install -m 0755 "$PEKIT_WORKSPACE_ROOT/_peiroot_/net-entry.sh" \
    "$PEKIT_SANDBOX_ROOT/usr/libexec/peiroot/entry"
}

if [ "${PEKIT_COMMAND:-}:${PEKIT_TARGET:-}" = build:vendor ]; then
  selection=$(python3 - "$PEKIT_DEPENDENCIES_FILE" <<'PYDEPS'
import json, sys
with open(sys.argv[1]) as f:
    providers = json.load(f)["all_providers"]
native = providers.get("peipkg", {})
if native:
    root, deps = "native", dict(native)
    # Only what the acquisition machinery itself needs: a shell for the
    # entry, python3 for the resolver, and resolvd's NSS shim for it to
    # answer through. Recipes declare every tool their commands use, as in
    # any native root; nothing else is ambient.
    infrastructure = ["org.git.kernel.dash", "org.mozilla.ca-certificates",
                      "org.python.python3", "dev.peios.resolvd-nss"]
else:
    if providers and "apt" not in providers:
        sys.exit("vendor acquisition requires declared apt dependencies")
    root, deps = "debian", dict(providers.get("apt", {}))
    infrastructure = ["ca-certificates"]
    if "cargo" in deps or "rustc" in deps:
        infrastructure += ["cargo", "rustc", "git"]
# Acquisition infrastructure; recipe constraints always take precedence.
for name in infrastructure:
    deps.setdefault(name, "*")
print(root)
for name, constraint in sorted(deps.items()):
    print(name, constraint)
PYDEPS
  )
  root=$(printf '%s\n' "$selection" | sed -n 1p)
  PEKIT_DEPENDENCIES=$(printf '%s\n' "$selection" | sed 1d)
  export PEKIT_DEPENDENCIES
  if [ "$root" != native ]; then
    "$PEKIT_WORKSPACE_ROOT/_debroot_/enter.sh"
    entry
    exit 0
  fi
  "$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh"
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
"$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh"
entry
