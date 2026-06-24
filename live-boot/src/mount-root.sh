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
mkdir /sysroot.lower /sysroot.rw
# The squashfs ships no SDs (the build doesn't stamp them), so under KACS
# DENY_MISSING every file in it is locked. policy=synth-ephemeral makes KACS
# synthesize a default SD per inode in memory — ephemeral, not synth-persist,
# because a read-only squashfs can't accept a written-back SD.
mount -o loop,ro,policy=synth-ephemeral -t squashfs /sysroot.squashfs /sysroot.lower
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
