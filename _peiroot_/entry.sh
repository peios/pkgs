#!/bin/sh
# Pekit sandbox entry for the default native profile ([sandbox] entry). It runs
# inside the sandbox ahead of every target command and then execs it.
#
# Networked native acquisition roots also carry the build-root resolver
# (buildroot-resolver.py): Peios glibc resolves hosts only through resolvd's
# socket, and a sandbox runs no resolvd. It returns once its socket is
# listening and serves from a background child for this job only; bwrap
# kills that child with the rest of the job when the target exits.
set -eu
resolver=/usr/libexec/peiroot/buildroot-resolver.py
if [ -f "$resolver" ]; then
  python3 "$resolver" /etc/resolv.conf
fi
exec "$@"
