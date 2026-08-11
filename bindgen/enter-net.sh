#!/bin/sh
# Network-enabled variant of _peiroot_/enter.sh for SOURCE-MATERIALISATION
# stages only (bindgen's [build.vendor]: cargo vendor must reach
# crates.io). Keep in sync with _peiroot_/enter.sh — identical except:
#   * --share-net after --unshare-all (host network namespace),
#   * host resolv.conf and CA bundle ro-bound in (no ca-certificates
#     package exists yet; host trust anchors for a fetch stage match how
#     pekit itself downloads sources),
#   * CARGO_HOME under /tmp.
# Build stages must NOT use this env — the pristine rung is offline by
# design; that's what peipkg.env.pekit.toml is for.
set -eu
script=${1:?missing wrapped command}
: "${PEKIT_WORKSPACE_ROOT:?peipkg.env requires a pekit workspace}"
pool="$PEKIT_WORKSPACE_ROOT/_pkgsOut_"

work=$(mktemp -d "${TMPDIR:-/tmp}/peiroot.XXXXXX")
trap 'rm -rf "$work"' EXIT INT TERM

{
  printf 'schema = 1\narch = "x86_64"\nsource_date = "2026-01-01T00:00:00Z"\n'
  printf 'local_packages = ["%s/*.peipkg"]\n' "$pool"
  printf '[[package]]\nname = "fsbase"\nversion = "*"\n'
  printf '%s\n' "${PEKIT_DEPENDENCIES:-}" | while read -r name constraint; do
    [ -n "$name" ] || continue
    printf '[[package]]\nname = "%s"\nversion = "%s"\n' "$name" "${constraint:-*}"
  done
} > "$work/root.toml"

peipkg-compose build "$work/root.toml" --out "$work/root"

status=0
bwrap \
  --die-with-parent \
  --unshare-all \
  --share-net \
  --uid 0 --gid 0 \
  --bind "$work/root" / \
  --dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --ro-bind /etc/resolv.conf /etc/resolv.conf \
  --ro-bind /etc/ssl/certs /etc/ssl/certs \
  --bind "$PEKIT_WORKSPACE_ROOT" "$PEKIT_WORKSPACE_ROOT" \
  --chdir "$PWD" \
  --clearenv \
  --setenv PATH /usr/bin \
  --setenv HOME /tmp \
  --setenv CARGO_HOME /tmp/cargo \
  --setenv FORCE_UNSAFE_CONFIGURE 1 \
  /usr/bin/sh -euc "$script" || status=$?
exit $status
