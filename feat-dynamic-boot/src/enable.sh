#!/usr/bin/sh
# dynamic-boot / enable — clear the watcher services' Disabled flag.
#
# This makes them eligible to run; peinit starts them on the next boot (a live
# registry reload re-reads the definition but does not retroactively launch a
# newly-enabled service). Re-runnable.
set -eu

reg set Machine/System/Services/mkirf-watch Disabled dword:0
reg set Machine/System/Services/mkuki-watch Disabled dword:0

echo "dynamic-boot: enabled mkirf-watch and mkuki-watch (start on next boot)"
