#!/bin/sh
# dynamic-boot / install — create the two watcher services, disabled.
#
# feat runs this as whoever invoked it (no escalation), so writing
# Machine\System\Services needs that token to have authority over the Machine
# hive; KACS enforces it. enable/disable later toggle the Disabled flag these
# services are created with; uninstall deletes them.
#
# reg accepts both \ and / as key separators — we use / to keep the JSON free of
# backslash escaping inside the heredocs.
set -eu

# The kernel image ships beside its own modules at
# /usr/lib/modules/<ver>/vmlinuz-<ver>; the service needs a concrete --kernel
# to start from. Sorting on the whole path is still version order, since <ver>
# appears in both the directory and the filename. mkuki watches the enclosing
# tree, so a later kernel swap still triggers a rebuild.
kernel="$(ls -1 /usr/lib/modules/*/vmlinuz-* 2>/dev/null | sort -V | tail -n1 || true)"
if [ -z "$kernel" ]; then
  echo "dynamic-boot: no /usr/lib/modules/<ver>/vmlinuz-* kernel found" >&2
  exit 1
fi

# mkirf watcher: repack /boot/initramfs into the boot cpio on every change.
# Simple service, Alive readiness (a foreground watcher never sends READY=1),
# boot-started, created Disabled.
reg apply - <<'EOF'
{ "keys": [ { "path": "Machine/System/Services/mkirf-watch", "values": [
  { "name": "ImagePath", "type": "sz", "data": "/bin/mkirf" },
  { "name": "Arguments", "type": "multi", "data": ["--watch", "--compress", "zstd", "/boot/initramfs", "/system/boot/initramfs.cpio.zst"] },
  { "name": "Type", "type": "dword", "data": 0 },
  { "name": "Readiness", "type": "dword", "data": 1 },
  { "name": "Triggers", "type": "multi", "data": ["boot"] },
  { "name": "Identity", "type": "sz", "data": "SYSTEM" },
  { "name": "Disabled", "type": "dword", "data": 1 }
] } ] }
EOF

# mkuki watcher: rebuild the UKI when the kernel, the cpio, or the cmdline file
# changes. (Unquoted heredoc so $kernel expands; the JSON has no backslashes to
# be mangled, since we use / separators.)
reg apply - <<EOF
{ "keys": [ { "path": "Machine/System/Services/mkuki-watch", "values": [
  { "name": "ImagePath", "type": "sz", "data": "/bin/mkuki" },
  { "name": "Arguments", "type": "multi", "data": ["--watch", "--kernel", "$kernel", "--initramfs", "/system/boot/initramfs.cpio.zst", "--cmdline-file", "/usr/share/live-boot/cmdline", "--out", "/boot/efi/EFI/BOOT/BOOTX64.EFI"] },
  { "name": "Type", "type": "dword", "data": 0 },
  { "name": "Readiness", "type": "dword", "data": 1 },
  { "name": "Triggers", "type": "multi", "data": ["boot"] },
  { "name": "Identity", "type": "sz", "data": "SYSTEM" },
  { "name": "Disabled", "type": "dword", "data": 1 }
] } ] }
EOF

echo "dynamic-boot: created mkirf-watch and mkuki-watch (disabled)"
