#!/bin/sh
# Pass 1 of the milestone-2 Canadian cross: build a debian->peios
# cross-toolchain (binutils + gcc, host=debian, target=x86_64-linux-peios)
# against the composed Peios sysroot. This toolchain is BUILD-ONLY — it never
# ships. Its jobs are:
#   (a) build the peios target libs (libgcc/libstdc++) that Pass 2 ships, and
#   (b) compile the peios-host gcc/binutils binaries that Pass 2 ships.
#
# Why a cross at all (not a plain --target native build): host and target are
# the SAME configuration here (x86_64-linux-peios), but the toolchain that
# ships must be built by something that runs in the build environment while
# emitting code laid out for the peios root — a vendor cross. The pass-1
# tools run on the rung-1 Debian container (PEI-156); only their OUTPUT
# targets peios.
#
# Prereq: the sysroot must already be composed from our own artifacts:
#   cd pkgs/gcc && peipkg-compose build sysroot.toml --out _sysroot
#
# Run INSIDE the rung-1 Debian container via the companion wrapper (which
# supplies the host build deps and enters through _debroot_/enter.sh):
#   sh pkgs/gcc/_cross/run-pass1.sh
#
# Resumable: each stage skips configure when its build dir already has a
# Makefile, so re-runs continue the incremental build.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)   # pkgs/gcc/_cross
GCC_DIR=$(dirname "$SCRIPT_DIR")                           # pkgs/gcc
PKGS_DIR=$(dirname "$GCC_DIR")                             # pkgs

TARGET=x86_64-linux-peios
SYSROOT="$GCC_DIR/_sysroot"
CROSS="$SCRIPT_DIR/tools"
BUILD="$SCRIPT_DIR/build"
PATCH="$SCRIPT_DIR/config-sub-peios.sh"

BU_SRC=$(ls -d "$PKGS_DIR"/binutils/out/*/source/ 2>/dev/null | head -1)
GCC_SRC=$(ls -d "$PKGS_DIR"/gcc/out/*/source/ 2>/dev/null | head -1)

[ -n "$BU_SRC" ] && [ -f "$BU_SRC/configure" ] || { echo "cross: binutils source not fetched (run pekit build in pkgs/binutils)" >&2; exit 1; }
[ -n "$GCC_SRC" ] && [ -f "$GCC_SRC/configure" ] || { echo "cross: gcc source not fetched (run pekit build in pkgs/gcc)" >&2; exit 1; }
[ -f "$SYSROOT/usr/include/stdio.h" ] || { echo "cross: sysroot not composed at $SYSROOT (see header)" >&2; exit 1; }
[ -f "$SYSROOT/usr/lib/$TARGET/crti.o" ] || { echo "cross: sysroot missing crt objects at usr/lib/$TARGET" >&2; exit 1; }

# Memory-bounded parallelism (gcc's heaviest TUs hit ~1-2 GB): ~1 job / 1.5 GB,
# capped at the core count.
JOBS=$(nproc)
MEMJOBS=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1500000 ))
[ "$MEMJOBS" -lt "$JOBS" ] && JOBS=$MEMJOBS
[ "$JOBS" -lt 1 ] && JOBS=1

export PATH="$CROSS/bin:$PATH"

echo "cross: target=$TARGET jobs=$JOBS"
echo "cross: sysroot=$SYSROOT"
echo "cross: prefix=$CROSS"
echo "cross: binutils=$BU_SRC"
echo "cross: gcc=$GCC_SRC"

# ---------------------------------------------------------------------------
# Pass 1a: cross binutils (as/ld/ar for the peios target, run on nix).
# config.sub learns peios; no multiarch concern here — gcc passes ld the -L
# search dirs, so ld needs only --with-sysroot for the default prefix.
# ---------------------------------------------------------------------------
echo "=== cross-binutils ==="
sh "$PATCH" "$BU_SRC/config.sub"
mkdir -p "$BUILD/binutils"
cd "$BUILD/binutils"
if [ ! -f Makefile ]; then
	"$BU_SRC/configure" \
		--prefix="$CROSS" \
		--target="$TARGET" \
		--with-sysroot="$SYSROOT" \
		--disable-nls \
		--disable-werror \
		--enable-deterministic-archives \
		--enable-plugins \
		--with-system-zlib
fi
make -j"$JOBS"
make install

# ---------------------------------------------------------------------------
# Pass 1b: cross gcc (C/C++) + peios target libgcc/libstdc++, against the
# existing sysroot glibc (so it builds in one pass — no glibc chicken/egg).
#
# Two source edits, applied to the gcc tree before configure:
#   - config.sub learns peios (so --target validates).
#   - t-linux64/t-linux: gcc hardcodes the x86_64 multiarch dir as
#     x86_64-linux-gnu; rewrite it to x86_64-linux-peios so the driver searches
#     the sysroot's usr/lib/x86_64-linux-peios (where glibc actually lives).
#     Multiarch auto-enables here because the sysroot has usr/lib/*/crti.o.
# ---------------------------------------------------------------------------
echo "=== cross-gcc ==="
sh "$PATCH" "$GCC_SRC/config.sub"
for tf in gcc/config/i386/t-linux64 gcc/config/i386/t-linux; do
	if grep -q 'linux-gnu' "$GCC_SRC/$tf"; then
		sed -i 's/x86_64-linux-gnu/x86_64-linux-peios/g; s/i386-linux-gnu/i386-linux-peios/g' "$GCC_SRC/$tf"
		echo "cross: rewrote multiarch dir in $tf"
	fi
done
mkdir -p "$BUILD/gcc"
cd "$BUILD/gcc"
if [ ! -f Makefile ]; then
	"$GCC_SRC/configure" \
		--prefix="$CROSS" \
		--target="$TARGET" \
		--with-sysroot="$SYSROOT" \
		--disable-multilib \
		--disable-bootstrap \
		--enable-languages=c,c++ \
		--enable-shared \
		--enable-threads=posix \
		--enable-__cxa_atexit \
		--disable-libsanitizer \
		--disable-werror
fi
make -j"$JOBS"
make install

echo
echo "cross: DONE. Toolchain at $CROSS/bin (prefix $TARGET-)"
echo "cross: verify with  sh $SCRIPT_DIR/verify-cross.sh"
