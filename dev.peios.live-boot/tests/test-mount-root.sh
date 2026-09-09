#!/usr/bin/sh
set -eu

recipe_root=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
hook="$recipe_root/src/mount-root.sh"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

fail() {
    printf 'live-boot test: %s\n' "$*" >&2
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

assert_mount_log() {
    mount_log=$(cat "$log/mount.args")
    case "$mount_log" in
        *"$1"*) ;;
        *) fail "mount log does not contain '$1': $mount_log" ;;
    esac
}

new_case() {
    case_dir=$(mktemp -d "$scratch/case.XXXXXX")
    root="$case_dir/root"
    tools="$case_dir/tools"
    log="$case_dir/log"
    mkdir -p "$root/usr/libexec/prelude" "$root/sys/block" "$root/dev" "$root/mnt" "$tools" "$log"
    ln -s "$recipe_root/tests/fixtures/hook-log.sh" "$root/usr/libexec/prelude/hook-log.sh"
    ln -s "$(command -v cat)" "$tools/cat"
    ln -s "$(command -v mkdir)" "$tools/mkdir"
    unset mock_medium_dev mock_squashfs_status mock_tmpfs_status || true
    unset mock_overlay_status mock_seed_status mock_move_status || true
}

enable_runtime() {
    for tool in mount umount seed-sd sleep; do
        ln -s "$recipe_root/tests/fixtures/$tool" "$tools/$tool"
    done
}

add_device() {
    : > "$root/sys/block/$1"
    : > "$root/dev/$1"
}

run_hook() {
    set +e
    output=$(
        cd "$case_dir"
        PEIOS_LIVE_BOOT_TEST_ROOT="$root" \
        PEIOS_LIVE_BOOT_TEST_LOG="$log" \
        PEIOS_LIVE_BOOT_MEDIUM_DEV="${mock_medium_dev:-}" \
        PEIOS_LIVE_BOOT_SQUASHFS_STATUS="${mock_squashfs_status:-0}" \
        PEIOS_LIVE_BOOT_TMPFS_STATUS="${mock_tmpfs_status:-0}" \
        PEIOS_LIVE_BOOT_OVERLAY_STATUS="${mock_overlay_status:-0}" \
        PEIOS_LIVE_BOOT_SEED_STATUS="${mock_seed_status:-0}" \
        PEIOS_LIVE_BOOT_MOVE_STATUS="${mock_move_status:-0}" \
        PEIOS_LIVE_BOOT_RETRY_LIMIT="${retry_limit:-3}" \
        PATH="$tools" \
        "$hook" 2>&1
    )
    status=$?
    set -e
}

# The test seam cannot redirect the hook through a relative path.
set +e
output=$(PEIOS_LIVE_BOOT_TEST_ROOT=relative "$hook" 2>&1)
status=$?
set -e
assert_status 2
assert_output 'PEIOS_LIVE_BOOT_TEST_ROOT must be absolute'

# A missing declared runtime tool is diagnosed as package damage.
new_case
run_hook
assert_status 1
assert_output 'no mount in the initramfs'

# Device discovery waits only for the configured budget and reports why the
# root was not mounted. The production default remains 50 attempts at 100 ms.
new_case
enable_runtime
retry_limit=3
run_hook
unset retry_limit
assert_status 1
assert_output 'no boot medium carrying /rootfs.squashfs found after 3 attempts'
[ "$(cat "$log/sleep.count")" = 2 ] || fail 'unexpected retry sleep count'

# The scan ignores a non-medium disk, selects the ISO carrying rootfs.squashfs,
# mounts the two layers, stamps the security descriptor, and moves the medium.
new_case
enable_runtime
add_device vda
add_device vdb
mock_medium_dev="$root/dev/vdb"
run_hook
assert_status 0
assert_output "OK live-boot: mounted boot medium $root/dev/vdb at /mnt/medium"
assert_output 'OK live-boot: medium available at /media/peios'
assert_mount_log "-t iso9660 -o ro $root/dev/vda $root/mnt/medium"
assert_mount_log "-t iso9660 -o ro $root/dev/vdb $root/mnt/medium"
assert_mount_log "-o loop,ro,policy=synth-ephemeral -t squashfs $root/mnt/medium/rootfs.squashfs $root/mnt/rootfs.lower"
assert_mount_log "-t tmpfs tmpfs $root/mnt/rootfs.rw"
assert_mount_log "-t overlay overlay -o lowerdir=$root/mnt/rootfs.lower,upperdir=$root/mnt/rootfs.rw/upper,workdir=$root/mnt/rootfs.rw/work $root/mnt/rootfs"
assert_mount_log "--move $root/mnt/medium $root/mnt/rootfs/media/peios"
case "$(cat "$log/seed-sd.args")" in
    *"$root/mnt/rootfs.rw") ;;
    *) fail 'seed-sd did not target the tmpfs upper' ;;
esac

# Moving the medium is a convenience; failure warns but does not discard an
# otherwise usable live root.
new_case
enable_runtime
add_device vda
mock_medium_dev="$root/dev/vda"
mock_move_status=32
run_hook
assert_status 0
assert_output 'WARN live-boot: could not carry the medium into the new root'

# A load-bearing layer failure is fatal and attributed to the failing stage.
new_case
enable_runtime
add_device vda
mock_medium_dev="$root/dev/vda"
mock_squashfs_status=32
run_hook
assert_status 1
assert_output 'FAIL live-boot: could not mount rootfs.squashfs'

[ "$(cat "$recipe_root/src/cmdline")" = 'loglevel=4 init=/bin/peinit2' ] ||
    fail 'the live-system cmdline template drifted'

printf '%s\n' 'live-boot hook tests passed'
