#!/usr/bin/sh
# /// hook
# provides = ["root-mounted"]
# ///
#
# Mount the real root as an overlay: read-only squashfs at the bottom,
# tmpfs scratch on top. Prelude pivots into the merged view at /sysroot,
# so userspace sees a writable Linux root while the shipped squashfs
# stays byte-for-byte the trusted artifact. Writes accumulate in the
# tmpfs upper and evaporate on reboot; a disk-backed install would swap
# the upper for a partition without changing the overlay shape.
set -eu

# prelude runs hooks with PATH=/usr/bin:/bin, so the peiosutils tools (mkdir,
# mount) and seed-sd resolve without the hook setting PATH itself.
mkdir /medium /sysroot.lower /sysroot.rw
# Find and mount the boot medium — the ISO9660 that carries the rootfs squashfs
# as a file. The squashfs lives here, not in the initramfs, so the whole OS
# never has to fit in RAM: the loop device below reads its blocks off the medium
# on demand. /medium therefore stays mounted for the session — prelude's chroot
# doesn't unmount it, so the loop keeps reading from it after the pivot.
#
# We can't resolve the medium by LABEL=: the initramfs has no udev, so
# libblkid's /dev/disk/by-label lookup is empty (and a hybrid GPT image hides
# the whole-disk ISO9660 label behind its partition table anyway). Instead scan
# the whole-disk block devices (/sys/block lists disks, not their partitions)
# and mount the one whose ISO9660 holds /sysroot.squashfs. iso9660 is SD-less,
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
        if mount -t iso9660 -o ro "$dev" /medium 2>/dev/null; then
            if [ -e /medium/sysroot.squashfs ]; then
                found="$dev"
                break
            fi
            umount /medium 2>/dev/null || true
        fi
    done
    [ -n "$found" ] && break
    tries=$((tries + 1))
    if [ "$tries" -ge 50 ]; then
        echo "live-boot: no boot medium carrying /sysroot.squashfs found after 5s" >&2
        exit 1
    fi
    sleep 0.1
done
echo "live-boot: mounted boot medium $found at /medium"
# The squashfs ships no SDs (the build doesn't stamp them), so under KACS
# DENY_MISSING every file in it is locked. policy=synth-ephemeral makes KACS
# synthesize a default SD per inode in memory — ephemeral, not synth-persist,
# because a read-only squashfs can't accept a written-back SD.
mount -o loop,ro,policy=synth-ephemeral -t squashfs /medium/sysroot.squashfs /sysroot.lower
mount -t tmpfs tmpfs /sysroot.rw

# A freshly-mounted tmpfs root has no SD xattr; under KACS DENY_MISSING
# the mkdirs immediately below would fail. Seed the SYSTEM-owned default
# first; the OI|CI ACE on it makes KACS inheritance derive a child SD
# for every directory and file we create here.
seed-sd /sysroot.rw

mkdir /sysroot.rw/upper /sysroot.rw/work
mount -t overlay overlay \
    -o lowerdir=/sysroot.lower,upperdir=/sysroot.rw/upper,workdir=/sysroot.rw/work \
    /sysroot
