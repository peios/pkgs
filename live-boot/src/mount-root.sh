#!/bin/sh
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

mkdir /sysroot.lower /sysroot.rw
mount -o loop,ro -t squashfs /sysroot.squashfs /sysroot.lower
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
