#!/usr/bin/sh
# /// hook
# contributes = ["rootfs-strata-ready"]
# after = ["rootfs-ready"]
# ///
#
# Establish the base StrataFS views inside the MOUNTED ROOT, after a hook has
# mounted it and before prelude pivots into it. The mirror of this package's
# other hook, which does the same job for the initramfs.
#
# `after` rather than `requires`: this hook decorates a root, it does not need
# one to exist for the image to be valid. A hard requirement would make the
# package unbuildable in an image carrying no root-mount hook at all, which is
# a legitimate thing to compose — and an image that genuinely has no root
# already fails on prelude's own check with a clearer message than a build
# error about capabilities.
#
# The chroot is not incidental. Mounting `/mnt/rootfs/lcl/...` from the
# initramfs namespace would bake that prefix into stratafs's recorded
# configuration and into /proc/self/mountinfo, leaving stale initramfs paths in
# a system that has pivoted away from it. Mounting from inside makes every
# stratum path canonical.
set -eu

# Mountpoints are topology, not package storage — no package owns /bin — so
# they are created rather than shipped. On a live system these land in the
# overlay's upper; on an installed one they are recreated idempotently each
# boot. Their descriptors inherit from the real root.
/usr/bin/mkdir -p \
    /mnt/rootfs/bin \
    /mnt/rootfs/sbin \
    /mnt/rootfs/lib \
    /mnt/rootfs/libexec \
    /mnt/rootfs/share \
    /mnt/rootfs/include \
    /mnt/rootfs/etc \
    /mnt/rootfs/conf

mount_view() {
    target=$1
    stack=$2
    echo "stratafs-base: mounting $target in the root"
    /usr/bin/chroot /mnt/rootfs /usr/bin/mount \
        -t stratafs none "$target" -o "strata=$stack"
}

# Operator storage is the create stratum and highest-precedence provider for
# ordinary views. Vendor storage is read-only *through the view* but remains
# independently writable through /usr by the package manager.
mount_view /bin     '/lcl/bin+create:/usr/bin+ro+am'
mount_view /sbin    '/lcl/sbin+create:/usr/sbin+ro+am'
mount_view /lib     '/lcl/lib+create:/usr/lib/x86_64-linux-peios+ro'
mount_view /libexec '/lcl/libexec+create:/usr/libexec+ro+am'
mount_view /share   '/lcl/share+create:/usr/share+ro+am'
mount_view /include '/lcl/include+create:/usr/include+ro+am'

# Reconciled registry output is authoritative when it supplies an /etc name.
# Other local configuration is created in /lcl/etc, above vendor defaults. This
# is the one view that differs from the initramfs's: there is a registry here,
# and /system/retc is where its output is projected.
#
# /conf has no reconciled tier because native software reads the registry
# directly rather than through a file.
mount_view /etc  '/system/retc:/lcl/etc+create:/usr/etc+ro+am'
mount_view /conf '/lcl/conf+create:/usr/conf+ro+am'
