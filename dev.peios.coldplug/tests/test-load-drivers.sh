#!/usr/bin/sh
set -eu

recipe_root=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
hook="$recipe_root/src/load-drivers.sh"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

fail() {
    printf 'coldplug test: %s\n' "$*" >&2
    exit 1
}

assert_status() {
    [ "$status" -eq "$1" ] || fail "status $status, want $1; output: $output"
}

assert_output() {
    case "$output" in
        *"$1"*) ;;
        *) fail "output does not contain '$1': $output" ;;
    esac
}

new_case() {
    case_dir=$(mktemp -d "$scratch/case.XXXXXX")
    root="$case_dir/root"
    tools="$case_dir/tools"
    mkdir -p "$root/usr/libexec/prelude" "$root/proc" "$root/sys/bus" "$root/tmp" "$tools"
    cp "$recipe_root/tests/fixtures/hook-log.sh" "$root/usr/libexec/prelude/hook-log.sh"
    ln -s "$recipe_root/tests/fixtures/uname" "$tools/uname"
    for tool in cat comm cut mktemp rm sort tr wc; do
        ln -s "$(command -v "$tool")" "$tools/$tool"
    done
}

enable_modprobe() {
    ln -s "$recipe_root/tests/fixtures/modprobe" "$tools/modprobe"
}

run_hook() {
    set +e
    output=$(
        cd "$case_dir"
        PEIOS_COLDPLUG_TEST_ROOT="$root" \
        PEIOS_COLDPLUG_TEST_LOG="$case_dir/modprobe.args" \
        PEIOS_COLDPLUG_MODPROBE_STATUS="${mock_status:-0}" \
        PATH="$tools" \
        "$hook" 2>&1
    )
    status=$?
    set -e
}

# Missing kmod is a package-integrity failure.
new_case
run_hook
assert_status 1
assert_output 'FAIL load-drivers: no modprobe in the initramfs'

# A module-free image and a machine with no modalias-bearing devices both
# decline their contribution rather than pretending work occurred.
new_case
enable_modprobe
run_hook
assert_status 69
assert_output 'SKIP load-drivers: no module tree at /lib/modules/test-release'

new_case
enable_modprobe
mkdir -p "$root/lib/modules/test-release"
run_hook
assert_status 69
assert_output 'SKIP load-drivers: no modaliases under /sys/bus'

# Aliases are sorted, deduplicated, and passed literally. The matching file in
# cwd makes this fail if shell pathname expansion is accidentally re-enabled.
new_case
enable_modprobe
mkdir -p "$root/lib/modules/test-release" \
    "$root/sys/bus/pci/devices/a" "$root/sys/bus/pci/devices/b" \
    "$root/sys/bus/usb/devices/c"
printf '%s\n' 'pci:*' > "$root/sys/bus/pci/devices/a/modalias"
printf '%s\n' 'z-alias' > "$root/sys/bus/pci/devices/b/modalias"
printf '%s\n' 'pci:*' > "$root/sys/bus/usb/devices/c/modalias"
printf '%s\n' 'existing 1 0 - Live 0x0' > "$root/proc/modules"
: > "$case_dir/pci:expanded"
run_hook
assert_status 0
[ "$(cat "$case_dir/modprobe.args")" = '-a -b -q pci:* z-alias' ] ||
    fail "modprobe arguments were not literal, sorted and unique"
assert_output 'OK load-drivers: 2 aliases; loaded: newmodule'

# A module refusing to load is reported by the downstream root-mount result,
# not promoted to an unrelated coldplug boot failure.
mock_status=1
printf '%s\n' 'existing 1 0 - Live 0x0' > "$root/proc/modules"
run_hook
assert_status 0
assert_output 'OK load-drivers: 2 aliases; nothing new to load'

printf '%s\n' 'coldplug hook tests passed'
