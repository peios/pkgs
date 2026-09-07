#!/bin/sh
# Release-image gate for glibc's non-configurable dynamic and static NSS paths.
# Run after authd and resolvd are ready, with the static probe built from the
# adjacent composed-nss.c against the exact glibc-static revision and supplied
# as $1 (default: /share/glibc-static-nss-probe).
set -eu

probe=${1:-/share/glibc-static-nss-probe}
libdir=/usr/lib/x86_64-linux-peios

test -r "$libdir/libnss_peios.so.2"
test -r "$libdir/libnss_peios_net.so.2"
test -x "$probe"

passwd_name=$(getent passwd SYSTEM)
passwd_id=$(getent passwd 0)
test "$(printf '%s\n' "$passwd_name" | awk -F: '{print $1 ":" $3}')" = SYSTEM:0
test "$passwd_id" = "$passwd_name"

group_name=$(getent group Everyone)
group_id=$(getent group 100)
test "$(printf '%s\n' "$group_name" | awk -F: '{print $1 ":" $3}')" = Everyone:100
test "$group_id" = "$group_name"

# Supplementary groups are authority state as well; require at least one
# resolved group beyond the queried principal name.
test "$(getent initgroups SYSTEM | awk '{print NF}')" -gt 1

if getent shadow SYSTEM || getent gshadow SYSTEM; then
  echo 'glibc: fixed-empty shadow database returned an entry' >&2
  exit 1
fi

getent hosts localhost >/dev/null
"$probe"
