#!/bin/sh
# Select the authoritative boot command line at service startup, then keep the
# UKI current as its kernel, initramfs, or command line changes.
set -eu

# Tests may place a complete synthetic filesystem below an absolute prefix.
# Production service definitions do not set this variable, so every path below
# resolves in the real root.
root=${PEIOS_DYNAMIC_BOOT_TEST_ROOT:-}
case "$root" in
    ''|/*) ;;
    *)
        echo "dynamic-boot: PEIOS_DYNAMIC_BOOT_TEST_ROOT must be absolute" >&2
        exit 2
        ;;
esac

installed_cmdline=$root/lcl/etc/boot/cmdline
vendor_cmdline=$root/usr/share/live-boot/cmdline
if [ -s "$installed_cmdline" ]; then
    cmdline=$installed_cmdline
elif [ -s "$vendor_cmdline" ]; then
    cmdline=$vendor_cmdline
else
    echo "dynamic-boot: no non-empty boot command line at /lcl/etc/boot/cmdline or /usr/share/live-boot/cmdline" >&2
    exit 1
fi

exec "$root/usr/bin/mkuki" \
    --watch \
    --kernel-dir "$root/usr/lib/modules" \
    --initramfs "$root/system/boot/initramfs.cpio.zst" \
    --cmdline-file "$cmdline" \
    --out "$root/boot/efi/EFI/BOOT/BOOTX64.EFI"
