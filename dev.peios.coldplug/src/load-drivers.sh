#!/usr/bin/sh
# /// hook
# contributes = ["rootfs-ready"]
# ///
#
# Load the driver for every device already enumerated by the kernel. A device
# manager repeats this continuously on the real root; this hook is the one-shot
# initramfs equivalent needed before a root-mount hook looks for storage.
set -eu

# Tests place a synthetic initramfs below an absolute prefix. Prelude clears
# the hook environment, so production always uses the empty default and sees
# the real root. Keeping the seam here lets tests exercise the installed script
# byte-for-byte without mounting over the host's /sys and /proc.
test_root=${PEIOS_COLDPLUG_TEST_ROOT:-}
case "$test_root" in
    ""|/*) ;;
    *) echo "load-drivers: PEIOS_COLDPLUG_TEST_ROOT must be absolute" >&2; exit 2 ;;
esac
root_path() { printf '%s%s\n' "$test_root" "$1"; }

# shellcheck source=/dev/null
. "$(root_path /usr/libexec/prelude/hook-log.sh)"
hook_log_init load-drivers

command -v modprobe >/dev/null 2>&1 || {
    log_fail "no modprobe in the initramfs; dev.peios.coldplug-irf depends on org.kernel.kmod"
    exit 1
}

release=$(uname -r)
module_root=$(root_path "/lib/modules/$release")
if [ ! -d "$module_root" ]; then
    # A module-free image is legitimate when every required driver is built in.
    log_skip "no module tree at /lib/modules/$release; nothing to load"
    exit 69
fi

sys_bus=$(root_path /sys/bus)
aliases=$(
    for dev in "$sys_bus"/*/devices/*; do
        [ -r "$dev/modalias" ] || continue
        cat "$dev/modalias"
    done | sort -u
)
if [ -z "$aliases" ]; then
    log_skip "no modaliases under /sys/bus; nothing to load"
    exit 69
fi

tmp_root=$(root_path /tmp)
work=$(mktemp -d "$tmp_root/load-drivers.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
before="$work/before"
after="$work/after"
proc_modules=$(root_path /proc/modules)
cut -d' ' -f1 "$proc_modules" | sort > "$before"

# -a loads every argument and continues through aliases that resolve to no
# module; -b honours the blacklist; -q suppresses normal unmatched aliases.
# Modaliases contain glob metacharacters by design. Disable pathname expansion
# only while expanding the newline-delimited list so those bytes reach modprobe
# literally instead of matching a coincidentally named file in the hook's cwd.
set -f
# shellcheck disable=SC2086
modprobe -a -b -q $aliases || true
set +f

cut -d' ' -f1 "$proc_modules" | sort > "$after"
loaded=$(comm -13 "$before" "$after" | tr '\n' ' ')
n=$(printf '%s\n' "$aliases" | wc -l)
if [ -n "$loaded" ]; then
    log_ok "$n aliases; loaded: $loaded"
else
    # A module load failure is diagnostic, not independently fatal. The
    # root-mount hook decides whether an unavailable driver prevents boot.
    log_ok "$n aliases; nothing new to load"
fi
