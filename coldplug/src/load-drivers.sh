#!/usr/bin/sh
# /// hook
# contributes = ["rootfs-ready"]
# ///
#
# Coldplug: load the driver for every device the kernel has already found.
#
# The kernel discovers hardware on its own — it walks PCI, USB, ACPI and the
# rest and emits a uevent per device carrying a MODALIAS — but it never loads a
# driver for what it finds. request_module() serves only what the kernel asks
# for by name (a filesystem, a netdev name); binding a driver to a device is
# userspace's job, and on a running system it is the device manager's. In the
# initramfs there is no device manager and no need for one: the devices that
# matter are all present before PID 1 runs, so a single pass over what the
# kernel has enumerated is the whole job. Anything that appears later is the
# real root's concern.
#
# Every enumerated device is a symlink under /sys/bus/<bus>/devices/, and the
# ones a module can drive carry a `modalias` file. Collecting those and handing
# the set to modprobe is exactly what `udevadm trigger` does at coldplug, minus
# the daemon. Read from /sys/bus rather than walking /sys/devices because the
# bus directories are flat, while the device tree is full of symlinks
# (subsystem, driver, firmware_node) that a naive walk would follow forever.
#
# Contributes to rootfs-ready: that is how a hook runs BEFORE the root is
# mounted (boot-hooks: "contributes is how a hook runs before something"). The
# root-mount hooks do not name this one — they predate it — and a `requires`
# from them would make an initramfs without this hook unbuildable, which is
# wrong for a VM whose disk driver is built in. Ordering among contributors is
# by file name, and this one sorts before mount-root*.sh; the storage drivers
# then probe asynchronously, which the root-mount hooks already wait out.
set -eu

# Everything below /usr/bin is package storage; prelude runs hooks with
# PATH=/usr/bin so modprobe (kmod) and the peiosutils tools resolve. modprobe
# looks under /lib/modules, a StrataFS view assembled by the initramfs-ready
# hooks this one is implicitly ordered after.
command -v modprobe >/dev/null 2>&1 || {
    echo "load-drivers: no modprobe in the initramfs; coldplug-irf depends on kmod" >&2
    exit 1
}

release=$(uname -r)
if [ ! -d "/lib/modules/$release" ]; then
    # An initramfs with no module tree for this kernel has nothing to load.
    # That is a legitimate image — every driver built in — so decline rather
    # than fail: "nothing needed doing here" completes our part of the
    # conjunction.
    echo "load-drivers: no module tree at /lib/modules/$release; nothing to load"
    exit 69
fi

aliases=$(
    for dev in /sys/bus/*/devices/*; do
        [ -r "$dev/modalias" ] || continue
        cat "$dev/modalias"
    done | sort -u
)
if [ -z "$aliases" ]; then
    echo "load-drivers: no modaliases under /sys/bus; nothing to load"
    exit 0
fi

before=/tmp/load-drivers.before
after=/tmp/load-drivers.after
cut -d' ' -f1 /proc/modules | sort > "$before"

# -a  treat every argument as a module to load, and keep going past ones
#     that do not resolve — most aliases match nothing, by design
# -b  honour the blacklist, as the device manager would
# -q  do not report the ones that match nothing; that is the normal case
#
# Failures are deliberately not fatal. An alias whose module refuses to load
# (a signature the kernel rejects, a probe that fails) is a driver that will
# not be available, and whether that matters is for the root-mount hook to
# decide — it is the one that knows which disk it needs. Halting here would
# turn "no driver for the sound card" into an unbootable machine.
# shellcheck disable=SC2086
modprobe -a -b -q $aliases || true

cut -d' ' -f1 /proc/modules | sort > "$after"
loaded=$(comm -13 "$before" "$after" | tr '\n' ' ')
rm -f "$before" "$after"
n=$(printf '%s\n' "$aliases" | wc -l)
if [ -n "$loaded" ]; then
    echo "load-drivers: $n aliases; loaded: $loaded"
else
    echo "load-drivers: $n aliases; nothing new to load"
fi
