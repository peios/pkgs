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

# There is no "is this my boot?" check here, and that is the design rather
# than an omission. This hook used to read `root=` off the kernel command line
# and stand aside when it found one, because both root-mount hooks shipped in
# every initramfs and one of them had to lose at runtime.
#
# Presence of the package is the selector now: a live image carries live-boot,
# an installed system carries disk-boot, and the installer swaps one for the
# other. So a hook that is here was wanted, and it acts. That is why
# live-boot-irf declares a conflict with disk-boot-irf — the invariant that
# exactly one root-mount hook exists moved from a runtime check into the
# package manager, which can enforce it before a boot rather than during one.

# prelude runs hooks with PATH=/usr/bin, so the peiosutils tools (mkdir,
# mount) and seed-sd resolve without the hook setting PATH itself.
mkdir /mnt/medium /mnt/rootfs.lower /mnt/rootfs.rw
# Find and mount the boot medium — the ISO9660 that carries the rootfs squashfs
# as a file. The squashfs lives here, not in the initramfs, so the whole OS
# never has to fit in RAM: the loop device below reads its blocks off the medium
# on demand. The medium therefore stays mounted for the whole session — the last
# step of this hook moves it into the new root at /media/peios, so the loop keeps
# reading from it after the pivot AND the booted system can reach it.
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

# --- the medium, carried into the new root -----------------------------------
# prelude mount-moves only /proc, /sys and /dev into the new root and then
# CHROOTS into it (it cannot pivot_root onto the kernel rootfs). Everything
# else the initramfs mounted — including this medium — stays in a namespace
# the booted system has no path to. So a live system could not read the
# medium it booted from, which is a strange thing for a live system not to be
# able to do: the medium is the one piece of storage it is guaranteed to have.
#
# Moving it here rather than rescanning later is the point. This hook has
# already identified the right device, out of every block device on the
# machine, by the only reliable test (does its ISO9660 carry rootfs.squashfs).
# Anything doing that again in userspace would be reimplementing that scan
# against a system where the answer is already known.
#
# MS_MOVE, not a bind: one mount, relocated. A bind would leave the original
# in the initramfs namespace, where prelude's cleanup walk would step around
# it forever.
#
# The move does not disturb the loop device backing /mnt/rootfs.lower. A loop
# device holds an open file, and an open file does not care what path it was
# opened through.
#
# /media is fsbase's, shipped as an empty directory in the squashfs; the
# per-medium subdirectory is created in the overlay's tmpfs upper, where
# seed-sd's inheritable ACE gives it a descriptor. Under /media rather than
# /run because this outlives no reboot but does outlive peinit mounting its
# own tmpfs over /run, and because /media is where a mounted medium belongs.
#
# Failure here is NOT fatal. Every earlier step in this hook is load-bearing —
# without them there is no root to boot. This one is a convenience, and a boot
# that reaches a login prompt with an unreachable medium is far better than no
# boot at all. It says so and continues.
# Both steps are guarded: this script runs under `set -e`, so an unguarded
# mkdir failure would abort the boot the paragraph above just promised not to.
if mkdir -p /mnt/rootfs/media/peios && mount --move /mnt/medium /mnt/rootfs/media/peios; then
    echo "live-boot: medium available at /media/peios"
else
    echo "live-boot: could not carry the medium into the new root; /media/peios will be empty" >&2
fi
