#!/bin/sh
# Kernel-delegate variant of _peiroot_/enter.sh (PEI-158). Keep in sync —
# identical except:
#   * the stage CWD is bind-mounted when it lies outside the workspace:
#     a delegate build runs with CWD at the fetched/local pkm source tree
#     while outputs live under pkgs/kernel/out — the same dual-mount
#     pkm's own docker wrap does ($PWD + $PEKIT_ROOT);
#   * the pkm toolchain knobs for composed roots ride in as env:
#       PKM_LLVM=1      kbuild uses unversioned LLVM tool names (upstream
#                       installs ship no Debian-style -18 suffixes),
#       PKM_HOSTCC=gcc  host tools stay on the native toolchain (clang's
#                       driver does not know the peios userspace layout),
#       RUST_LIB_SRC    the kernel's default assumes literal lib/rustlib;
#                       our rust package ships src under the triplet dir.
#     See pkm/build/compile-kernel.sh for the knob contract.
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

# Delegate dual-mount: bind the source-tree CWD when the workspace bind
# does not already cover it.
case "$PWD/" in
  "$PEKIT_WORKSPACE_ROOT"/*) set -- ;;
  *) set -- --bind "$PWD" "$PWD" ;;
esac

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
  "$@" \
  --chdir "$PWD" \
  --clearenv \
  --setenv PATH /usr/bin \
  --setenv HOME /tmp \
  --setenv FORCE_UNSAFE_CONFIGURE 1 \
  ${PKM_JOBS:+--setenv PKM_JOBS "$PKM_JOBS"} \
  --setenv PKM_LLVM 1 \
  --setenv PKM_HOSTCC gcc \
  --setenv RUST_LIB_SRC /usr/lib/x86_64-linux-peios/rustlib/src/rust/library \
  /usr/bin/sh -euc "$script" || status=$?
exit $status
