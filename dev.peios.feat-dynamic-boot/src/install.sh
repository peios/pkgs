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

# mkirf watcher: repack /boot/initramfs into the boot cpio on every change.
# Simple service, Alive readiness (a foreground watcher never sends READY=1),
# boot-started, created Disabled.
reg apply - <<'EOF'
{ "keys": [ { "path": "Machine/System/Services/mkirf-watch", "values": [
  { "name": "ImagePath", "type": "sz", "data": "/usr/bin/mkirf" },
  { "name": "Arguments", "type": "multi", "data": ["--watch", "--compress", "zstd", "--exclude", "var/state/peipkg", "--exclude", "lcl/conf/peipkg", "/boot/initramfs", "/system/boot/initramfs.cpio.zst"] },
  { "name": "Type", "type": "dword", "data": 0 },
  { "name": "Readiness", "type": "dword", "data": 1 },
  { "name": "Triggers", "type": "multi", "data": ["boot"] },
  { "name": "Identity", "type": "sz", "data": "SYSTEM" },
  { "name": "Disabled", "type": "dword", "data": 1 }
] } ] }
EOF

# mkuki watcher: the launcher selects the installed command line at service
# startup, then mkuki follows the unique kernel below /usr/lib/modules. This
# avoids freezing the service definition to whichever release was installed
# when the feature was added.
reg apply - <<'EOF'
{ "keys": [ { "path": "Machine/System/Services/mkuki-watch", "values": [
  { "name": "ImagePath", "type": "sz", "data": "/usr/libexec/features/dynamic-boot/watch-uki.sh" },
  { "name": "Arguments", "type": "multi", "data": [] },
  { "name": "Type", "type": "dword", "data": 0 },
  { "name": "Readiness", "type": "dword", "data": 1 },
  { "name": "Triggers", "type": "multi", "data": ["boot"] },
  { "name": "Identity", "type": "sz", "data": "SYSTEM" },
  { "name": "Disabled", "type": "dword", "data": 1 }
] } ] }
EOF

echo "dynamic-boot: created mkirf-watch and mkuki-watch (disabled)"
