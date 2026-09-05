#!/bin/sh
# Rung 1 of the PEI-126 self-host ladder: run a pekit target inside a
# pristine Debian container instead of on the bare host.
#
# pekit invokes this through debian.env.pekit.toml's [wrap]; $1 is the
# fully assembled target script (export prelude + target command). The
# container installs exactly the apt packages the recipe declares
# (PEKIT_DEPENDENCIES, one "name constraint" per line), then drops from
# root to the invoking uid/gid to run the script, so staged files land
# on the host with the right owner. The workspace is bound at its host
# path, which keeps every literal PEKIT_* path in the script valid
# inside. --rm makes the root pristine per invocation; the named volumes
# only cache apt downloads and lists so repeat runs are cheap.
set -eu
script=${1:?missing wrapped command}
: "${PEKIT_WORKSPACE_ROOT:?debian.env requires a pekit workspace}"
deps=$(printf '%s\n' "${PEKIT_DEPENDENCIES:-}" | awk 'NF {print $1}' | tr '\n' ' ')
exec docker run --rm \
  -v "$PEKIT_WORKSPACE_ROOT:$PEKIT_WORKSPACE_ROOT" \
  -v pekit-debroot-apt-archives:/var/cache/apt/archives \
  -v pekit-debroot-apt-lists:/var/lib/apt/lists \
  -w "$PWD" \
  -e DEBROOT_DEPS="$deps" \
  -e DEBROOT_UID="$(id -u)" \
  -e DEBROOT_GID="$(id -g)" \
  debian:trixie \
  sh -euc '
    rm -f /etc/apt/apt.conf.d/docker-clean
    if [ -n "$DEBROOT_DEPS" ]; then
      find /var/lib/apt/lists -maxdepth 1 -name "*_Packages*" -mmin -1440 | grep -q . || apt-get update -q
      DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends $DEBROOT_DEPS
    fi

    # setpriv accepts numeric identities that are absent from the container
    # databases, but build/test programs reasonably expect getpwuid(3),
    # getgrgid(3), ~ expansion and Path.home() to work. Give the invoking
    # identity an ephemeral entry before dropping privileges.
    getent group "$DEBROOT_GID" >/dev/null ||
      printf "pekit-build-%s:x:%s:\n" "$DEBROOT_GID" "$DEBROOT_GID" >> /etc/group
    getent passwd "$DEBROOT_UID" >/dev/null ||
      printf "pekit-build-%s:x:%s:%s:Pekit build user:/tmp:/bin/sh\n" \
        "$DEBROOT_UID" "$DEBROOT_UID" "$DEBROOT_GID" >> /etc/passwd

    exec setpriv --reuid "$DEBROOT_UID" --regid "$DEBROOT_GID" --clear-groups env HOME=/tmp sh -euc "$1"
  ' debroot "$script"
