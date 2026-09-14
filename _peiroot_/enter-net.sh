#!/bin/sh
# Acquisition uses a clean Debian root with declared tools and TLS trust.
# The host root, home, rustup, cargo credentials and caches are never mounted.
set -eu
if [ "${PEKIT_COMMAND:-}:${PEKIT_TARGET:-}" = build:vendor ]; then
  PEKIT_DEPENDENCIES=$(python3 - "$PEKIT_DEPENDENCIES_FILE" <<'PYDEPS'
import json, sys
with open(sys.argv[1]) as f:
    providers = json.load(f)["all_providers"]
if providers and "apt" not in providers:
    sys.exit("vendor acquisition requires declared apt dependencies")
deps = dict(providers.get("apt", {}))
# Acquisition infrastructure; recipe constraints always take precedence.
infrastructure = ["ca-certificates"]
if "cargo" in deps or "rustc" in deps:
    infrastructure += ["cargo", "rustc", "git"]
for name in infrastructure:
    deps.setdefault(name, "*")
for name, constraint in sorted(deps.items()):
    print(name, constraint)
PYDEPS
  )
  export PEKIT_DEPENDENCIES
  exec "$PEKIT_WORKSPACE_ROOT/_debroot_/enter.sh"
fi
exec "$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh"
