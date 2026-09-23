#!/bin/sh
# Compose the declared native dependencies into the sandbox root; called by
# enter.sh for every target. Pekit owns worker isolation.
set -eu
: "${PEKIT_SANDBOX_ROOT:?Pekit must supply a private root destination}"
: "${PEKIT_WORKSPACE_ROOT:?the native root requires a pekit workspace}"
repo=$(python3 "$PEKIT_WORKSPACE_ROOT/_peiroot_/snapshot-repository.py")
# Repository trust is intentionally pinned out of band, in repository.anchor
# (shared with the Debian preparer's catalogue overlay). Update it only as part
# of an explicit repository-key rotation ceremony.
repo_anchor=$(cat "$PEKIT_WORKSPACE_ROOT/_peiroot_/repository.anchor")
case "$repo_anchor" in
  *[!0-9a-f]*|"") echo "peiroot: invalid repository trust anchor" >&2; exit 1 ;;
esac
[ "${#repo_anchor}" -eq 64 ] || { echo "peiroot: invalid repository trust anchor" >&2; exit 1; }

[ -f "$repo/repo.json" ] || {
  echo "peiroot: signed package repository is missing: $repo" >&2
  exit 1
}

work=$(mktemp -d "${TMPDIR:-/tmp}/peiroot.XXXXXX")
trap 'rm -rf "$work"' EXIT INT TERM

{
  printf 'schema = 1\narch = "x86_64"\nsource_date = "2026-01-01T00:00:00Z"\n'
  printf '[[repository]]\nname = "peios"\nbase_url = "file://%s"\n' "$repo"
  printf 'priority = 10\nsignature_policy = "required"\ntrust_anchors = ["%s"]\n' "$repo_anchor"
  printf '[[package]]\nname = "dev.peios.fsbase"\nversion = "*"\n'
  printf '%s\n' "${PEKIT_DEPENDENCIES:-}" | while read -r name constraint; do
    [ -n "$name" ] || continue
    printf '[[package]]\nname = "%s"\nversion = "%s"\n' "$name" "${constraint:-*}"
  done
} > "$work/root.toml"

# --dangerously-bypass-path-restrictions: this root always includes
# dev.peios.fsbase, whose whole job is to mint the mountpoint tree (/dev, /proc,
# /run, /sys, /tmp) that the payload layout rules otherwise protect.
# dev.peios.fsbase declares special_system_package; this flag is the composer's
# half of that two-key exemption. A build root is precisely the case
# it exists for, and it grants nothing to a package that has not
# declared itself special.
#
# --record-xattrs: package build roots are disposable bwrap inputs, not images
# that will boot, and the unprivileged maintainer process cannot set security.*
# attributes on the host filesystem. Preserve compose's complete descriptor
# output in the temporary work area rather than weakening package validation;
# it is discarded together with the root after the build target exits.
peipkg-compose build "$work/root.toml" --out "$PEKIT_SANDBOX_ROOT" \
  --record-xattrs "$work/xattrs.jsonl" \
  --dangerously-bypass-path-restrictions

# Keep exact automatically selected dependency identities for this job.
record="$PEKIT_JOB_STATE/dependencies/$PEKIT_COMMAND-$PEKIT_TARGET"
mkdir -p "$record"
cp "$work/root.toml" "$work/root.lock.toml" "$record/"

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
# dev.peios.fsbase owns it as real package payload.
for view in bin sbin lib; do
  [ -e "$PEKIT_SANDBOX_ROOT/$view" ] || ln -s "usr/$view" "$PEKIT_SANDBOX_ROOT/$view"
done

# /etc is also a StrataFS view on a booted Peios system. Packages put vendor
# defaults in /usr/etc, registry-derived values in /system/retc, and local
# overrides in /lcl/etc; the build root has no StrataFS mount, so materialise
# an effective snapshot in the same low-to-high precedence order. This is only
# sandbox state and is discarded with the root. It makes configure scripts and
# test suites observe the runtime paths without allowing package payloads to
# claim /etc itself.
mkdir -p "$PEKIT_SANDBOX_ROOT/etc"
for tier in usr/etc system/retc lcl/etc; do
  [ -d "$PEKIT_SANDBOX_ROOT/$tier" ] || continue
  cp -a "$PEKIT_SANDBOX_ROOT/$tier/." "$PEKIT_SANDBOX_ROOT/etc/"
done

# A build sandbox has a synthetic uid/gid and no boot-time identity or network
# initialisation. Give libc and upstream test suites the minimal matching
# static databases they would otherwise receive from those runtime layers.
# These files exist only in the disposable build root and are never packaged.
[ -e "$PEKIT_SANDBOX_ROOT/etc/passwd" ] || cat > "$PEKIT_SANDBOX_ROOT/etc/passwd" <<'EOF'
root:x:0:0:root:/root:/bin/sh
peibuild:x:1000:1000:Peios package builder:/tmp:/bin/sh
EOF
[ -e "$PEKIT_SANDBOX_ROOT/etc/group" ] || cat > "$PEKIT_SANDBOX_ROOT/etc/group" <<'EOF'
root:x:0:
peibuild:x:1000:
EOF
[ -e "$PEKIT_SANDBOX_ROOT/etc/hosts" ] || cat > "$PEKIT_SANDBOX_ROOT/etc/hosts" <<'EOF'
127.0.0.1 localhost
::1 localhost ip6-localhost ip6-loopback
EOF
