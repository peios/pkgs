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
# intrinsic. bwrap then maps the host build identity to the fixed,
# unprivileged peibuild identity and binds the workspace at its host path,
# keeping every literal PEKIT_* path in the script valid inside. Presenting
# the single-ID user namespace as uid 0 would make programs legitimately
# expect supplementary uid/gid mappings and privileges that the hermetic root
# does not provide. Package ownership remains independent: peipkg normalises
# the packed result to root. The root is composed fresh per invocation and
# discarded — pristine by construction.
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

# --dangerously-bypass-path-restrictions: this root always includes
# fsbase, whose whole job is to mint the mountpoint tree (/dev, /proc,
# /run, /sys, /tmp) that the payload layout rules otherwise protect.
# fsbase declares special_system_package; this flag is the composer's
# half of that two-key exemption. A build root is precisely the case
# it exists for, and it grants nothing to a package that has not
# declared itself special.
peipkg-compose build "$work/root.toml" --out "$work/root" \
  --dangerously-bypass-path-restrictions

# Root-level runtime views. A booted Peios gets /bin, /sbin and /lib from
# StrataFS (stratafs-base-topo's mount hook); peipkg-compose used to mint
# them as usr-merge symlinks until that intrinsic was deliberately removed,
# on the grounds that filesystem topology is not a composer side effect.
# Correct — but a bwrap build root has no StrataFS, and essentially every
# upstream build system hardcodes /bin/sh (autotools' configure, generated
# libtool, make's default SHELL). Without these the rung cannot run a single
# autotools recipe.
#
# So the sandbox mints them itself, which is where the responsibility now
# sits. /lib -> usr/lib, the shape every package in the farm was built and
# verified against — and now also what the StrataFS hooks mount at runtime.
# They used to point /lib at usr/lib/<triplet>, which resolved no library the
# loader could not already find by absolute path, while breaking the two
# consumers that do use /lib: kmod has /lib/modules compiled in and the
# kernel's firmware loader searches /lib/firmware. Sandbox and running system
# agree again, so a package built here sees the paths it will see on a booted
# system. /lib64 is skipped —
# fsbase 1.0.0-3 owns it as real package payload.
for view in bin sbin lib; do
  [ -e "$work/root/$view" ] || ln -s "usr/$view" "$work/root/$view"
done

# /etc is also a StrataFS view on a booted Peios system. Packages put vendor
# defaults in /usr/etc, registry-derived values in /system/retc, and local
# overrides in /lcl/etc; the build root has no StrataFS mount, so materialise
# an effective snapshot in the same low-to-high precedence order. This is only
# sandbox state and is discarded with the root. It makes configure scripts and
# test suites observe the runtime paths without allowing package payloads to
# claim /etc itself.
mkdir -p "$work/root/etc"
for tier in usr/etc system/retc lcl/etc; do
  [ -d "$work/root/$tier" ] || continue
  cp -a "$work/root/$tier/." "$work/root/etc/"
done

status=0
bwrap \
  --die-with-parent \
  --unshare-all \
  --uid 1000 --gid 1000 \
  --bind "$work/root" / \
  --dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --bind "$PEKIT_WORKSPACE_ROOT" "$PEKIT_WORKSPACE_ROOT" \
  --chdir "$PWD" \
  --clearenv \
  --setenv PATH /usr/bin \
  --setenv HOME /tmp \
  --setenv USER peibuild \
  --setenv LOGNAME peibuild \
  --setenv PEKIT_NATIVE_ROOT 1 \
  /usr/bin/sh -euc "$script" || status=$?
exit $status
