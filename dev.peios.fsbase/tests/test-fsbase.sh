#!/usr/bin/sh
set -eu

recipe_root=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
initramfs_hook="$recipe_root/src/mount-initramfs-stratafs-base.sh"
rootfs_hook="$recipe_root/src/mount-rootfs-stratafs-base.sh"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

fail() {
    printf 'fsbase test: %s\n' "$*" >&2
    exit 1
}

assert_output() {
    case "$output" in
        *"$1"*) ;;
        *) fail "output does not contain '$1': $output" ;;
    esac
}

assert_no_output() {
    case "$output" in
        *"$1"*) fail "output unexpectedly contains '$1': $output" ;;
        *) ;;
    esac
}

assert_status() {
    [ "$status" -eq "$1" ] || fail "status $status, want $1; output: $output"
}

# The build output is the filesystem contract. Check the ABI link, the common
# storage shape, and representative directories that must remain root-specific.
: "${PEKIT_OUT:?PEKIT_OUT is required}"
for stage in main irf; do
    [ -L "$PEKIT_OUT/$stage/lib64" ] || fail "$stage/lib64 is not a symlink"
    [ "$(readlink "$PEKIT_OUT/$stage/lib64")" = usr/lib/x86_64-linux-peios ] ||
        fail "$stage/lib64 has the wrong target"
    for path in dev proc sys run/lock tmp var/state/secrets lcl/bin usr/bin usr/lib/modules usr/lib/firmware; do
        [ -d "$PEKIT_OUT/$stage/$path" ] || fail "$stage is missing $path"
    done
done
for path in run/services system/retc system/boot boot data home srv opt media; do
    [ -d "$PEKIT_OUT/main/$path" ] || fail "main is missing $path"
    [ ! -e "$PEKIT_OUT/irf/$path" ] || fail "irf unexpectedly contains $path"
done
for path in usr/libexec/prelude/hooks.d lcl/libexec/prelude/hooks.d; do
    [ -d "$PEKIT_OUT/irf/$path" ] || fail "irf is missing $path"
done

# Both scripts must remain valid Dash programs.
/usr/bin/sh -n "$initramfs_hook"
/usr/bin/sh -n "$rootfs_hook"

new_case() {
    case_dir=$(mktemp -d "$scratch/case.XXXXXX")
    root="$case_dir/root"
    log="$case_dir/log"
    mkdir -p "$root/usr/bin" "$root/usr/libexec/prelude" "$log"
    cp "$recipe_root/tests/fixtures/hook-log.sh" "$root/usr/libexec/prelude/hook-log.sh"
    ln -s "$(command -v mkdir)" "$root/usr/bin/mkdir"
    ln -s "$recipe_root/tests/fixtures/mount" "$root/usr/bin/mount"
    ln -s "$recipe_root/tests/fixtures/chroot" "$root/usr/bin/chroot"
    : > "$log/mount.args"
    : > "$log/chroot.args"
}

run_hook() {
    hook=$1
    set +e
    output=$(
        PEIOS_FSBASE_TEST_ROOT="$root" \
        PEIOS_FSBASE_TEST_LOG="$log" \
        PEIOS_FSBASE_FAIL_TARGET="${fail_target:-}" \
        "$hook" 2>&1
    )
    status=$?
    set -e
}

# A relative isolation prefix must fail before the hook touches any path.
for hook in "$initramfs_hook" "$rootfs_hook"; do
    set +e
    output=$(PEIOS_FSBASE_TEST_ROOT=relative "$hook" 2>&1)
    status=$?
    set -e
    assert_status 2
    assert_output 'PEIOS_FSBASE_TEST_ROOT must be absolute'
done

# The initramfs hook creates and mounts all eight base views with the exact
# canonical strata. Success is reported only after the mount returns zero.
new_case
run_hook "$initramfs_hook"
assert_status 0
[ "$(wc -l < "$log/mount.args")" -eq 8 ] || fail "initramfs did not mount eight views"
expected="-t stratafs none $root/bin -o strata=/lcl/bin+create:/usr/bin+ro+am
-t stratafs none $root/sbin -o strata=/lcl/sbin+create:/usr/sbin+ro+am
-t stratafs none $root/lib -o strata=/lcl/lib+create:/usr/lib+ro
-t stratafs none $root/libexec -o strata=/lcl/libexec+create:/usr/libexec+ro+am
-t stratafs none $root/share -o strata=/lcl/share+create:/usr/share+ro+am
-t stratafs none $root/include -o strata=/lcl/include+create:/usr/include+ro+am
-t stratafs none $root/etc -o strata=/lcl/etc+create:/usr/etc+ro+am
-t stratafs none $root/conf -o strata=/lcl/conf+create:/usr/conf+ro+am"
[ "$(cat "$log/mount.args")" = "$expected" ] || fail "initramfs mount graph drifted"
assert_output 'OK stratafs-base: mounted /conf'

new_case
fail_target="$root/lib"
run_hook "$initramfs_hook"
unset fail_target
assert_status 1
assert_no_output 'OK stratafs-base: mounted /lib'
[ "$(wc -l < "$log/mount.args")" -eq 3 ] || fail "initramfs continued after mount failure"

# The mounted-root hook chroots before mounting, retains canonical paths inside
# that root, includes the reconciled /system/retc tier, and obeys the same
# report-after-success rule.
new_case
run_hook "$rootfs_hook"
assert_status 0
[ "$(wc -l < "$log/chroot.args")" -eq 8 ] || fail "rootfs did not mount eight views"
expected="$root/mnt/rootfs /usr/bin/mount -t stratafs none /bin -o strata=/lcl/bin+create:/usr/bin+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /sbin -o strata=/lcl/sbin+create:/usr/sbin+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /lib -o strata=/lcl/lib+create:/usr/lib+ro
$root/mnt/rootfs /usr/bin/mount -t stratafs none /libexec -o strata=/lcl/libexec+create:/usr/libexec+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /share -o strata=/lcl/share+create:/usr/share+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /include -o strata=/lcl/include+create:/usr/include+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /etc -o strata=/system/retc:/lcl/etc+create:/usr/etc+ro+am
$root/mnt/rootfs /usr/bin/mount -t stratafs none /conf -o strata=/lcl/conf+create:/usr/conf+ro+am"
[ "$(cat "$log/chroot.args")" = "$expected" ] || fail "rootfs mount graph drifted"
assert_output 'OK stratafs-base: mounted /conf in the root'

new_case
fail_target=/lib
run_hook "$rootfs_hook"
unset fail_target
assert_status 1
assert_no_output 'OK stratafs-base: mounted /lib in the root'
[ "$(wc -l < "$log/chroot.args")" -eq 3 ] || fail "rootfs continued after mount failure"

printf '%s\n' 'fsbase topology and hook tests passed'
