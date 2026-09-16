#!/bin/sh
# build:vendor is the only networked target. It acquires sources in a clean
# root chosen by the acquisition toolchain the recipe declares:
#
#   * Native, for Go. Go's netgo resolver reads the resolv.conf Pekit copies
#     into a networked root, so the declared org.golang.go acquires modules
#     without any Peios service running. TLS trust comes from the declared
#     Mozilla bundle, which trustd composes on a booted system but nothing
#     composes in a build root.
#   * Debian, for everything else. Peios glibc routes host lookup only through
#     resolvd, which a build root does not run, so Cargo (libcurl) and pip
#     cannot resolve a host natively. They acquire with declared apt tools.
#
# Compilation and tests always run offline in the native root. The host root,
# home, rustup, cargo credentials and caches are never mounted.
set -eu
if [ "${PEKIT_COMMAND:-}:${PEKIT_TARGET:-}" = build:vendor ]; then
  selection=$(python3 - "$PEKIT_DEPENDENCIES_FILE" <<'PYDEPS'
import json, sys
with open(sys.argv[1]) as f:
    providers = json.load(f)["all_providers"]
native = providers.get("peipkg", {})
if "org.golang.go" in native:
    root, deps = "native", dict(native)
    infrastructure = ["org.mozilla.ca-certificates"]
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
    exec "$PEKIT_WORKSPACE_ROOT/_debroot_/enter.sh"
  fi
  "$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh"
  trust="$PEKIT_SANDBOX_ROOT/etc/ssl/certs/ca-certificates.crt"
  if [ ! -e "$trust" ]; then
    bundle="$PEKIT_SANDBOX_ROOT/usr/share/ca-certificates/mozilla.crt"
    [ -s "$bundle" ] || {
      echo "peiroot: native acquisition root has no Mozilla trust bundle" >&2
      exit 1
    }
    mkdir -p "${trust%/*}"
    cp "$bundle" "$trust"
  fi
  exit 0
fi
exec "$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh"
