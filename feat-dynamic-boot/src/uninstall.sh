#!/usr/bin/sh
# dynamic-boot / uninstall — remove the watcher service definitions.
#
# feat disables before uninstalling, so by here the services are already marked
# Disabled; this deletes the keys entirely. -r --yes makes it non-interactive
# and robust if a service key ever grows subkeys. Tolerant of an already-absent
# key so re-running is harmless.
set -eu

reg del -r --yes Machine/System/Services/mkirf-watch || true
reg del -r --yes Machine/System/Services/mkuki-watch || true

echo "dynamic-boot: removed mkirf-watch and mkuki-watch"
