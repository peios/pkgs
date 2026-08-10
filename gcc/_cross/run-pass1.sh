#!/bin/sh
# Run Pass 1 (build-cross.sh) inside the rung-1 Debian container with the
# host build deps it needs: build-essential for everything, flex for gcc's
# git-checkout lexer regen, the host bignum dev packages for the pass-1
# cc1 (auto-detected — the pass-1 gcc runs HERE, so it links Debian's
# gmp/mpfr/mpc/isl), zlib1g-dev for the pass-1 binutils' --with-system-zlib,
# and texinfo so doc rules never trip the build.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PKGS_DIR=$(dirname "$(dirname "$SCRIPT_DIR")")
export PEKIT_WORKSPACE_ROOT="$PKGS_DIR"
export PEKIT_DEPENDENCIES='build-essential *
flex *
bison *
libgmp-dev *
libmpfr-dev *
libmpc-dev *
libisl-dev *
zlib1g-dev *
texinfo *'
cd "$PKGS_DIR"
exec "$PKGS_DIR/_debroot_/enter.sh" "sh $SCRIPT_DIR/build-cross.sh"
