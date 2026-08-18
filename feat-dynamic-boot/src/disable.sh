#!/bin/sh
# dynamic-boot / disable — set the watcher services' Disabled flag.
#
# Keeps the service definitions but marks them disabled; they will not start on
# the next boot. Re-runnable. (Stopping an already-running watcher this boot is
# a lifecycle-command concern, not this script's.)
set -eu

reg set Machine/System/Services/mkirf-watch Disabled dword:1
reg set Machine/System/Services/mkuki-watch Disabled dword:1

echo "dynamic-boot: disabled mkirf-watch and mkuki-watch"
