#!/bin/sh
# Network-capable source-materialisation wrapper for the inherited
# peipkg-net environment.
#
# Peios glibc deliberately routes host lookup only through resolvd. A pristine
# package-build root has neither a running Peios service manager nor resolvd,
# and bypassing that policy with nsswitch.conf is not possible or desirable.
# For build:vendor only, use the host's downloader/toolchain in a bwrap whose
# host root and recipe source are read-only, whose target output is the sole
# writable workspace path, and whose network namespace is shared. Cargo.lock
# and the crate checksums make this a source acquisition step; compilation and
# testing are delegated to the normal offline Peipkg root below.
set -eu
script=${1:?missing wrapped command}
: "${PEKIT_WORKSPACE_ROOT:?peipkg-net env requires a pekit workspace}"

if [ "${PEKIT_COMMAND:-}:${PEKIT_TARGET:-}" != "build:vendor" ]; then
  exec "$PEKIT_WORKSPACE_ROOT/_peiroot_/enter.sh" "$script"
fi

host_cargo=$(command -v cargo) || {
  echo "peipkg-net build:vendor requires cargo on the host" >&2
  exit 1
}
host_cargo_bin=${host_cargo%/*}
case "$host_cargo" in
  */.cargo/bin/cargo)
    host_home=${host_cargo%/.cargo/bin/cargo}
    host_rustup="$host_home/.rustup"
    ;;
  *)
    host_rustup=/nonexistent
    ;;
esac

status=0
bwrap \
  --die-with-parent \
  --unshare-all \
  --share-net \
  --uid 0 --gid 0 \
  --ro-bind / / \
  --dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --ro-bind "$PEKIT_WORKSPACE_ROOT" "$PEKIT_WORKSPACE_ROOT" \
  --bind "$PEKIT_OUT" "$PEKIT_OUT" \
  --chdir "$PWD" \
  --clearenv \
  --setenv PATH "$host_cargo_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
  --setenv HOME /tmp \
  --setenv CARGO_HOME /tmp/cargo \
  --setenv RUSTUP_HOME "$host_rustup" \
  /bin/sh -euc "$script" || status=$?
exit $status
