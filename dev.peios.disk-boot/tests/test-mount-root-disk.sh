#!/usr/bin/sh
set -eu

recipe_root=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
hook="$recipe_root/src/mount-root-disk.sh"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

fail() {
    printf 'disk-boot test: %s\n' "$*" >&2
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

assert_no_mount() {
    [ ! -e "$log/mount.args" ] || fail "mount unexpectedly ran: $(cat "$log/mount.args")"
}

new_case() {
    case_dir=$(mktemp -d "$scratch/case.XXXXXX")
    root="$case_dir/root"
    tools="$case_dir/tools"
    log="$case_dir/log"
    mkdir -p "$root/usr/libexec/prelude" "$root/proc" "$tools" "$log"
    cp "$recipe_root/tests/fixtures/hook-log.sh" "$root/usr/libexec/prelude/hook-log.sh"
    ln -s "$(command -v cat)" "$tools/cat"
    : > "$case_dir/lsblk.output"
    printf '%s\n' 'init=/bin/peinit2' > "$root/proc/cmdline"
    unset mock_fsck_status mock_mount_status mock_lsblk_status || true
}

enable_runtime() {
    for tool in lsblk mount sleep; do
        ln -s "$recipe_root/tests/fixtures/$tool" "$tools/$tool"
    done
}

enable_fsck() {
    ln -s "$recipe_root/tests/fixtures/fsck" "$tools/fsck"
}

run_hook() {
    set +e
    output=$(
        cd "$case_dir"
        PEIOS_DISK_BOOT_TEST_ROOT="$root" \
        PEIOS_DISK_BOOT_TEST_LOG="$log" \
        PEIOS_DISK_BOOT_LSBLK_OUTPUT="$case_dir/lsblk.output" \
        PEIOS_DISK_BOOT_LSBLK_STATUS="${mock_lsblk_status:-0}" \
        PEIOS_DISK_BOOT_FSCK_STATUS="${mock_fsck_status:-0}" \
        PEIOS_DISK_BOOT_MOUNT_STATUS="${mock_mount_status:-0}" \
        PEIOS_DISK_BOOT_RETRY_LIMIT="${retry_limit:-3}" \
        PATH="$tools" \
        "$hook" 2>&1
    )
    status=$?
    set -e
}

# The test seam cannot redirect the hook through a relative path.
set +e
output=$(PEIOS_DISK_BOOT_TEST_ROOT=relative "$hook" 2>&1)
status=$?
set -e
assert_status 2
assert_output 'PEIOS_DISK_BOOT_TEST_ROOT must be absolute'

# A missing declared runtime tool is diagnosed as package damage.
new_case
ln -s "$recipe_root/tests/fixtures/mount" "$tools/mount"
printf '%s\n' 'root=UUID=ROOT' > "$root/proc/cmdline"
run_hook
assert_status 1
assert_output 'no lsblk in the initramfs'
assert_no_mount

# An installed-system image without root=, or with an unsupported spelling,
# is broken rather than a hook that can decline in favour of another flavour.
new_case
enable_runtime
run_hook
assert_status 1
assert_output 'no root= on the cmdline'
assert_no_mount

new_case
enable_runtime
printf '%s\n' 'root=/not/a/device' > "$root/proc/cmdline"
run_hook
assert_status 1
assert_output "unsupported root= form '/not/a/device'"
assert_no_mount

# Last root= wins. Tag resolution uses the requested lsblk column, fsck is
# explicitly reported as absent, and mount receives the deny-missing policy.
new_case
enable_runtime
printf '%s\n' 'root=UUID=OLD root=LABEL=ROOT init=/bin/peinit2' > "$root/proc/cmdline"
printf '%s\n' '/dev/vda1 OTHER' '/dev/vda2 ROOT' > "$case_dir/lsblk.output"
run_hook
assert_status 0
assert_output 'OK disk-boot: root=LABEL=ROOT resolved to /dev/vda2'
assert_output 'WARN disk-boot: no fsck in the initramfs; relying on journal replay'
assert_output 'OK disk-boot: mounted /dev/vda2 at /mnt/rootfs'
[ "$(cat "$log/lsblk.args")" = '-p -n -l -o PATH,LABEL' ] ||
    fail "unexpected lsblk arguments: $(cat "$log/lsblk.args")"
[ "$(cat "$log/mount.args")" = '-o policy=deny-missing /dev/vda2 /mnt/rootfs' ] ||
    fail "unexpected mount arguments: $(cat "$log/mount.args")"

# A glob-looking tag is data, even when it matches a file in the hook's cwd.
new_case
enable_runtime
printf '%s\n' 'root=PARTUUID=*' > "$root/proc/cmdline"
printf '%s\n' '/dev/vda3 *' > "$case_dir/lsblk.output"
: > "$case_dir/expanded"
run_hook
assert_status 0
assert_output 'root=PARTUUID=* resolved to /dev/vda3'
[ "$(cat "$log/lsblk.args")" = '-p -n -l -o PATH,PARTUUID' ] ||
    fail "unexpected PARTUUID lsblk arguments"

# Device discovery retries only for the configured budget and never mounts an
# empty result. The production default remains 50 attempts at 100 ms.
new_case
enable_runtime
printf '%s\n' 'root=UUID=MISSING' > "$root/proc/cmdline"
retry_limit=3
run_hook
unset retry_limit
assert_status 1
assert_output 'no device matched root=UUID=MISSING after 3 attempts'
[ "$(cat "$log/sleep.count")" = 2 ] || fail "unexpected retry sleep count"
assert_no_mount

# fsck's conventional status 1 means it corrected errors and may proceed.
new_case
enable_runtime
enable_fsck
printf '%s\n' 'root=UUID=ROOT' > "$root/proc/cmdline"
printf '%s\n' '/dev/vda1 ROOT' > "$case_dir/lsblk.output"
mock_fsck_status=1
run_hook
assert_status 0
[ "$(cat "$log/fsck.args")" = '-p /dev/vda1' ] || fail "unexpected fsck arguments"
[ -e "$log/mount.args" ] || fail "mount did not run after corrected fsck"

# A reboot-required or uncorrected fsck result blocks the mount.
new_case
enable_runtime
enable_fsck
printf '%s\n' 'root=UUID=ROOT' > "$root/proc/cmdline"
printf '%s\n' '/dev/vda1 ROOT' > "$case_dir/lsblk.output"
mock_fsck_status=2
run_hook
assert_status 1
assert_output 'fsck /dev/vda1 failed (status 2)'
assert_no_mount

# Mount failure is attributed to the root-mount hook rather than left as a
# bare command exit from a set -e script.
new_case
enable_runtime
printf '%s\n' 'root=UUID=ROOT' > "$root/proc/cmdline"
printf '%s\n' '/dev/vda1 ROOT' > "$case_dir/lsblk.output"
mock_mount_status=32
run_hook
assert_status 1
assert_output 'could not mount /dev/vda1 at /mnt/rootfs'

[ "$(cat "$recipe_root/src/cmdline")" = 'loglevel=4 init=/bin/peinit2' ] ||
    fail 'the installed-system cmdline template drifted'

printf '%s\n' 'disk-boot hook tests passed'
