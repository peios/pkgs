#!/bin/sh
# Rung 2 of the PEI-126 self-host ladder: run a pekit target inside a
# pristine root composed entirely from our own signed pool.
#
# pekit invokes this through peipkg.env.pekit.toml's [wrap]; $1 is the
# fully assembled target script (export prelude + target command). The
# root is the dependency closure of exactly what the recipe declares
# (PEKIT_DEPENDENCIES, one "name constraint" per line) plus fsbase as
# the skeleton ground — peipkg-compose resolves it offline from
# _pkgsOut_, materialising claims (dash's /usr/bin/sh) and the usr-merge
# intrinsic. bwrap then enters it single-uid (peipkg normalises all
# ownership to root, so uid 0 inside is the whole ownership model) with
# the workspace bound at its host path, keeping every literal PEKIT_*
# path in the script valid inside. The root is composed fresh per
# invocation and discarded — pristine by construction.
#
# FORCE_UNSAFE_CONFIGURE: gnulib's configure refuses to run as root
# (tar, coreutils, ...). uid 0 inside is this rung's permanent ownership
# model (peipkg normalises everything to root) and the root is a
# throwaway, so the check protects nothing here.
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
  --uid 0 --gid 0 \
  --bind "$work/root" / \
  --dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --bind "$PEKIT_WORKSPACE_ROOT" "$PEKIT_WORKSPACE_ROOT" \
  --chdir "$PWD" \
  --clearenv \
  --setenv PATH /usr/bin \
  --setenv HOME /tmp \
  --setenv FORCE_UNSAFE_CONFIGURE 1 \
  /usr/bin/sh -euc "$script" || status=$?
exit $status
