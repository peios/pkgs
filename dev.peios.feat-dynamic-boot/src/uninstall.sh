#!/bin/sh
# dynamic-boot / uninstall — remove the watcher service definitions.
#
# feat disables before uninstalling, so by here the services are already marked
# Disabled; this deletes the keys entirely. -r --yes makes it non-interactive
# and robust if a service key ever grows subkeys. Tolerant of an already-absent
# key so re-running is harmless.
set -eu

remove_service() {
    key=$1
    if reg del -r --yes "$key"; then
        return 0
    else
        status=$?
    fi
    # reg's documented exit 2 is ENOENT. A recursive delete can also lose a
    # descendant concurrently: accept it only if this service key is absent.
    [ "$status" -eq 2 ] || return "$status"
    if reg info --no-follow "$key" >/dev/null; then
        return "$status"
    else
        status=$?
    fi
    [ "$status" -eq 2 ] || return "$status"
}

remove_service Machine/System/Services/mkirf-watch
remove_service Machine/System/Services/mkuki-watch

echo "dynamic-boot: removed mkirf-watch and mkuki-watch"
