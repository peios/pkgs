#!/usr/bin/sh
# /// hook
# contributes = ["initramfs-ready"]
# ///
#
# Assemble the base StrataFS views inside the INITRAMFS root — /bin, /sbin,
# /lib and the rest — so that everything after this point can use ordinary
# paths instead of reaching into package storage.
#
# This is the mirror of stratafs-base-topo's hook, which does the same job for
# the real root after it has been mounted. The initramfs is an independently
# executing root and needs its own views for the same reason it needs its own
# mountpoints and its own loader link: nothing it runs can borrow from a root
# that does not exist yet.
#
# `contributes = ["initramfs-ready"]` is what puts this first. Every hook that
# does not supply that capability is implicitly ordered after it, so a hook
# author gets these views without having to know this hook exists — and this
# hook is exempt from its own rule by being part of the capability rather than
# by declaring anything.
#
# Absolute package-storage paths throughout, deliberately: this hook runs
# BEFORE the views it creates, so /usr/bin/mkdir cannot be spelled `mkdir`
# here even though it can be in every hook that follows.
set -eu

# Tests place a synthetic initramfs below an absolute prefix. Prelude clears
# the hook environment, so production always uses the empty default and sees
# the real root. This lets the shipped hook exercise its absolute pre-view
# paths without touching the host's mount namespace.
test_root=${PEIOS_FSBASE_TEST_ROOT:-}
case "$test_root" in
    ""|/*) ;;
    *) printf '%s\n' "stratafs-base: PEIOS_FSBASE_TEST_ROOT must be absolute" >&2; exit 2 ;;
esac
root_path() { printf '%s%s\n' "$test_root" "$1"; }

# The shared console line format (prelude-hook-abi >= 3). Absolute path, like
# everything else in this hook: it runs BEFORE the views it creates.
# shellcheck source=/dev/null
. "$(root_path /usr/libexec/prelude/hook-log.sh)"
hook_log_init stratafs-base

# The mountpoints are topology, not package storage — no package owns /bin —
# so they are created here rather than shipped. They land in the initramfs's
# own ramfs and vanish with it.
"$(root_path /usr/bin/mkdir)" -p \
    "$(root_path /bin)" \
    "$(root_path /sbin)" \
    "$(root_path /lib)" \
    "$(root_path /libexec)" \
    "$(root_path /share)" \
    "$(root_path /include)" \
    "$(root_path /etc)" \
    "$(root_path /conf)"

mount_view() {
    target=$1
    stack=$2
    "$(root_path /usr/bin/mount)" -t stratafs none "$(root_path "$target")" \
        -o "strata=$stack"
    log_ok "mounted $target"
}

# Operator storage is the create stratum and highest-precedence provider for
# ordinary views. Vendor storage is read-only *through the view* but remains
# independently writable through /usr.
mount_view /bin     '/lcl/bin+create:/usr/bin+ro+am'
mount_view /sbin    '/lcl/sbin+create:/usr/sbin+ro+am'
# /usr/lib, NOT /usr/lib/<triplet> — see the note in the rootfs hook. It
# matters here too: kernel-modules-irf installs to /usr/lib/modules/<release>
# inside this root, and modprobe looks for /lib/modules/<release>.
mount_view /lib     '/lcl/lib+create:/usr/lib+ro'
mount_view /libexec '/lcl/libexec+create:/usr/libexec+ro+am'
mount_view /share   '/lcl/share+create:/usr/share+ro+am'
mount_view /include '/lcl/include+create:/usr/include+ro+am'

# /etc has no reconciled tier here, and that is the one place this hook
# deliberately differs from the real root's. There, /system/retc is the
# highest stratum — registry output projected into /etc — but the initramfs
# runs before registryd exists, and fsbase-irf does not even mint system/retc.
# Naming a stratum nothing produces would be a mount that fails at boot.
mount_view /etc  '/lcl/etc+create:/usr/etc+ro+am'
mount_view /conf '/lcl/conf+create:/usr/conf+ro+am'
