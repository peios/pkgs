#!/usr/bin/sh
set -eu

recipe_root=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

fail() {
    printf 'dynamic-boot test: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    grep -F -- "$2" "$1" >/dev/null || fail "$1 does not contain: $2"
}

# Capture registry invocations and imported JSON without needing a live Peios
# registry. The install contract should be independent of the host kernel.
tools=$scratch/tools
mkdir -p "$tools"
cat > "$tools/reg" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$PEIOS_DYNAMIC_BOOT_REG_LOG"
cat >> "$PEIOS_DYNAMIC_BOOT_REG_LOG"
EOF
chmod 0755 "$tools/reg"

reg_log=$scratch/registry.log
PEIOS_DYNAMIC_BOOT_REG_LOG=$reg_log PATH="$tools:$PATH" \
    "$recipe_root/src/install.sh" >/dev/null
assert_contains "$reg_log" 'apply -'
assert_contains "$reg_log" 'Machine/System/Services/mkirf-watch'
assert_contains "$reg_log" '"data": "/usr/bin/mkirf"'
assert_contains "$reg_log" '"--exclude", "var/state/peipkg"'
assert_contains "$reg_log" '"--exclude", "lcl/conf/peipkg"'
assert_contains "$reg_log" 'Machine/System/Services/mkuki-watch'
assert_contains "$reg_log" '"data": "/usr/libexec/features/dynamic-boot/watch-uki.sh"'
assert_contains "$reg_log" '"Identity", "type": "sz", "data": "SYSTEM"'
assert_contains "$reg_log" '"Disabled", "type": "dword", "data": 1'

PEIOS_DYNAMIC_BOOT_REG_LOG=$reg_log PATH="$tools:$PATH" \
    "$recipe_root/src/enable.sh" >/dev/null
assert_contains "$reg_log" 'set Machine/System/Services/mkirf-watch Disabled dword:0'
assert_contains "$reg_log" 'set Machine/System/Services/mkuki-watch Disabled dword:0'

PEIOS_DYNAMIC_BOOT_REG_LOG=$reg_log PATH="$tools:$PATH" \
    "$recipe_root/src/disable.sh" >/dev/null
assert_contains "$reg_log" 'set Machine/System/Services/mkirf-watch Disabled dword:1'
assert_contains "$reg_log" 'set Machine/System/Services/mkuki-watch Disabled dword:1'

PEIOS_DYNAMIC_BOOT_REG_LOG=$reg_log PATH="$tools:$PATH" \
    "$recipe_root/src/uninstall.sh" >/dev/null
assert_contains "$reg_log" 'del -r --yes Machine/System/Services/mkirf-watch'
assert_contains "$reg_log" 'del -r --yes Machine/System/Services/mkuki-watch'

# Exercise command-line selection and the complete mkuki argv in a synthetic
# root. The installed /lcl command line must win over the live-image fallback.
root=$scratch/root
mkdir -p "$root/usr/bin" "$root/usr/lib/modules" "$root/system/boot" \
    "$root/boot/efi/EFI/BOOT" "$root/lcl/etc/boot" \
    "$root/usr/share/live-boot"
cat > "$root/usr/bin/mkuki" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > "$PEIOS_DYNAMIC_BOOT_MKUKI_LOG"
EOF
chmod 0755 "$root/usr/bin/mkuki"
printf '%s\n' 'installed command line' > "$root/lcl/etc/boot/cmdline"
printf '%s\n' 'vendor command line' > "$root/usr/share/live-boot/cmdline"

mkuki_log=$scratch/mkuki.args
PEIOS_DYNAMIC_BOOT_TEST_ROOT=$root PEIOS_DYNAMIC_BOOT_MKUKI_LOG=$mkuki_log \
    "$recipe_root/src/watch-uki.sh"
assert_contains "$mkuki_log" '--watch'
assert_contains "$mkuki_log" '--kernel-dir'
assert_contains "$mkuki_log" "$root/usr/lib/modules"
assert_contains "$mkuki_log" "$root/lcl/etc/boot/cmdline"
if grep -F "$root/usr/share/live-boot/cmdline" "$mkuki_log" >/dev/null; then
    fail 'vendor command line won over installed command line'
fi

rm -f "$root/lcl/etc/boot/cmdline"
PEIOS_DYNAMIC_BOOT_TEST_ROOT=$root PEIOS_DYNAMIC_BOOT_MKUKI_LOG=$mkuki_log \
    "$recipe_root/src/watch-uki.sh"
assert_contains "$mkuki_log" "$root/usr/share/live-boot/cmdline"

rm -f "$root/usr/share/live-boot/cmdline"
if PEIOS_DYNAMIC_BOOT_TEST_ROOT=$root PEIOS_DYNAMIC_BOOT_MKUKI_LOG=$mkuki_log \
    "$recipe_root/src/watch-uki.sh" >"$scratch/missing.out" 2>&1; then
    fail 'watch launcher accepted a missing command line'
fi
assert_contains "$scratch/missing.out" 'no non-empty boot command line'

if PEIOS_DYNAMIC_BOOT_TEST_ROOT=relative "$recipe_root/src/watch-uki.sh" \
    >"$scratch/relative.out" 2>&1; then
    fail 'watch launcher accepted a relative test root'
fi
assert_contains "$scratch/relative.out" 'must be absolute'

for script in "$recipe_root"/src/*.sh; do
    /usr/bin/sh -n "$script"
    [ -x "$script" ] || fail "$script is not executable"
done

printf '%s\n' 'dynamic-boot feature tests passed'
