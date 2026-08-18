#!/usr/bin/sh
# /// hook
# contributes = ["rootfs-ready"]
# ///
#
# Mount an installed root filesystem directly at /mnt/rootfs. Unlike the live
# path there is no overlay: the partition is writable, so it is the real root
# and stacking a tmpfs on it would only throw away every write at reboot.
#
# `root=` is read for the device it names, not to decide whether this hook is
# wanted. That question is answered by the package being installed at all: a
# live image carries live-boot, an installed system carries disk-boot, and the
# installer swaps one for the other. live-boot-irf declares the conflict that
# keeps it to one.
#
# Which is why a missing `root=` is an ERROR here rather than a decline. There
# is no other hook to leave the root to, so an installed system whose UKI lost
# its `root=` is a broken image — and this hook is the only thing that knows
# it. Declining would hand prelude a boot with nothing mounted, which surfaces
# a stage later as the generic "no hook mounted a root filesystem" with the
# actual cause already forgotten.
set -eu

# prelude runs hooks with PATH=/usr/bin, so peiosutils (mount, lsblk) resolves
# without the hook setting PATH itself.

# --- the target ---------------------------------------------------------------
# Not "selection" any more: this reads which device to mount, not whether to.
# Last root= wins, matching the kernel's own handling of repeated parameters.
root_spec=
for word in $(cat /proc/cmdline); do
    case "$word" in
        root=*) root_spec="${word#root=}" ;;
    esac
done

if [ -z "$root_spec" ]; then
    echo "disk-boot: no root= on the cmdline; nothing names the root to mount" >&2
    exit 1
fi

# --- resolution --------------------------------------------------------------
# Tags are resolved with lsblk, which probes each device through libblkid
# rather than reading /dev/disk/by-uuid. That matters here: the initramfs runs
# no udev, so the by-* symlink directories are empty and the usual lookup finds
# nothing. Probing the devices themselves is the only thing that works.
find_by_tag() {
    tag=$1
    want=$2
    lsblk -p -n -l -o PATH,"$tag" 2>/dev/null | while read -r dev value; do
        if [ "$value" = "$want" ]; then
            printf '%s\n' "$dev"
            break
        fi
    done
}

resolve_root() {
    case "$1" in
        /dev/*)     [ -b "$1" ] && printf '%s\n' "$1" ;;
        UUID=*)     find_by_tag UUID "${1#UUID=}" ;;
        PARTUUID=*) find_by_tag PARTUUID "${1#PARTUUID=}" ;;
        LABEL=*)    find_by_tag LABEL "${1#LABEL=}" ;;
    esac
}

# Reject an unsupported form here rather than inside resolve_root: that runs in
# a command substitution, so an `exit` there would kill only the subshell and
# leave this script running with an empty result and a misleading error.
case "$root_spec" in
    /dev/*|UUID=*|PARTUUID=*|LABEL=*) ;;
    *)
        echo "disk-boot: unsupported root= form '$root_spec'" >&2
        exit 1
        ;;
esac

# Retry for a few seconds: storage drivers probe asynchronously, so the
# partition may not have appeared yet (virtio wins immediately; USB needs a
# beat). Same shape and budget as live-boot's medium scan.
#
# `|| true` is load-bearing under `set -e`: "not found yet" is the normal state
# of every iteration but the last, and resolve_root reports it by returning
# non-zero (a failed [ -b ], or `read` hitting EOF with no match). Without it
# the first miss would fail the boot instead of waiting for the disk.
dev=
tries=0
while [ -z "$dev" ]; do
    dev=$(resolve_root "$root_spec" || true)
    [ -n "$dev" ] && break
    tries=$((tries + 1))
    if [ "$tries" -ge 50 ]; then
        echo "disk-boot: no device matched root=$root_spec after 5s" >&2
        exit 1
    fi
    sleep 0.1
done
echo "disk-boot: root=$root_spec resolved to $dev"

# --- check -------------------------------------------------------------------
# fsck is the initramfs's job — peinit must never repair a root it is already
# running on. Peios does not yet put e2fsprogs in the initramfs, so this is
# conditional rather than mandatory, and says which way it went instead of
# leaving a silent gap. Without it an unclean filesystem still replays its
# journal at mount, which covers the ordinary crash; it does not cover real
# corruption.
if command -v fsck >/dev/null 2>&1; then
    # -p: repair only what can be fixed without asking. There is nobody to ask.
    fsck -p "$dev" || {
        status=$?
        # 1 = errors corrected, which is a success for our purposes. Anything
        # above that left the filesystem unfit to mount.
        if [ "$status" -gt 1 ]; then
            echo "disk-boot: fsck $dev failed (status $status)" >&2
            exit 1
        fi
    }
else
    echo "disk-boot: no fsck in the initramfs; relying on journal replay"
fi

# --- mount -------------------------------------------------------------------
# policy=deny-missing, not a synthesising class: an installed root carries real
# security descriptors — one stamped on the root inode by `mke2fs -E
# root_sddl=` at install time, the rest inherited from it or copied in — so a
# file without one is a fault to be surfaced, not a gap to be papered over.
# This is the whole reason installing beats running live: the access policy is
# a property of the filesystem rather than of the command that mounted it.
#
# No -t: the type is probed. Nothing here is ext-specific.
mount -o policy=deny-missing "$dev" /mnt/rootfs
echo "disk-boot: mounted $dev at /mnt/rootfs"
