#!/usr/bin/sh
# /// hook
# contributes = ["rootfs-ready"]
# ///
#
# Mount the real root as an overlay: read-only squashfs at the bottom,
# tmpfs scratch on top. Prelude pivots into the merged view at /mnt/rootfs,
# so userspace sees a writable Linux root while the shipped squashfs
# stays byte-for-byte the trusted artifact. Writes accumulate in the
# tmpfs upper and evaporate on reboot; a disk-backed install would swap
# the upper for a partition without changing the overlay shape.
set -eu

# This hook and disk-boot's both contribute to `rootfs-ready`, and both run.
# `root=` on the kernel command line decides which one acts: an installed UKI
# carries one, the live UKI does not.
#
# Standing aside is exit 69 — DECLINED — rather than an error, because prelude
# halts on errors and that would take down the boot this hook is standing
# aside FOR. Declining completes this hook's part of the conjunction without
# claiming to have mounted anything: nothing needed doing here.
#
# The runtime check is temporary. The intended shape is that an installed
# system simply does not have the live-boot package — the installer removes
# it — so package presence selects the boot path and no hook has to inspect
# the cmdline to discover whether it is wanted.
for word in $(cat /proc/cmdline); do
    case "$word" in
        root=*)
            echo "live-boot: root= on the cmdline; this is a disk boot, standing aside"
            exit 69
            ;;
    esac
done

# prelude runs hooks with PATH=/usr/bin, so the peiosutils tools (mkdir,
# mount) and seed-sd resolve without the hook setting PATH itself.
mkdir /mnt/medium /mnt/rootfs.lower /mnt/rootfs.rw
# Find and mount the boot medium — the ISO9660 that carries the rootfs squashfs
# as a file. The squashfs lives here, not in the initramfs, so the whole OS
# never has to fit in RAM: the loop device below reads its blocks off the medium
# on demand. /mnt/medium therefore stays mounted for the session — prelude's chroot
# doesn't unmount it, so the loop keeps reading from it after the pivot.
#
# We can't resolve the medium by LABEL=: the initramfs has no udev, so
# libblkid's /dev/disk/by-label lookup is empty (and a hybrid GPT image hides
# the whole-disk ISO9660 label behind its partition table anyway). Instead scan
# the whole-disk block devices (/sys/block lists disks, not their partitions)
# and mount the one whose ISO9660 holds /rootfs.squashfs. iso9660 is SD-less,
# but the kernel defaults it to a synthesized-ephemeral SD policy, so the mount
# needs no policy= option. Retry the whole scan for a few seconds: storage
# drivers probe asynchronously, so the medium may not have appeared yet (fast
# buses like virtio win immediately; USB needs a beat).
found=
tries=0
while [ -z "$found" ]; do
    for sysdev in /sys/block/*; do
        dev="/dev/${sysdev##*/}"
        [ -b "$dev" ] || continue
        if mount -t iso9660 -o ro "$dev" /mnt/medium 2>/dev/null; then
            if [ -e /mnt/medium/rootfs.squashfs ]; then
                found="$dev"
                break
            fi
            umount /mnt/medium 2>/dev/null || true
        fi
    done
    [ -n "$found" ] && break
    tries=$((tries + 1))
    if [ "$tries" -ge 50 ]; then
        echo "live-boot: no boot medium carrying /rootfs.squashfs found after 5s" >&2
        exit 1
    fi
    sleep 0.1
done
echo "live-boot: mounted boot medium $found at /mnt/medium"
# The squashfs ships no SDs (the build doesn't stamp them), so under KACS
# DENY_MISSING every file in it is locked. policy=synth-ephemeral makes KACS
# synthesize a default SD per inode in memory — ephemeral, not synth-persist,
# because a read-only squashfs can't accept a written-back SD.
mount -o loop,ro,policy=synth-ephemeral -t squashfs /mnt/medium/rootfs.squashfs /mnt/rootfs.lower
mount -t tmpfs tmpfs /mnt/rootfs.rw

# A freshly-mounted tmpfs root has no SD xattr; under KACS DENY_MISSING
# the mkdirs immediately below would fail. Seed the SYSTEM-owned default
# first; the OI|CI ACE on it makes KACS inheritance derive a child SD
# for every directory and file we create here.
seed-sd /mnt/rootfs.rw

mkdir /mnt/rootfs.rw/upper /mnt/rootfs.rw/work
mount -t overlay overlay \
    -o lowerdir=/mnt/rootfs.lower,upperdir=/mnt/rootfs.rw/upper,workdir=/mnt/rootfs.rw/work \
    /mnt/rootfs
