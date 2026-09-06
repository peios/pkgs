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
#   cd pkgs/org.gnu.gcc && peipkg-compose build sysroot.toml --out _sysroot
#
# Run INSIDE the rung-1 Debian container via the companion wrapper (which
# supplies the host build deps and enters through _debroot_/enter.sh):
#   sh pkgs/org.gnu.gcc/_cross/run-pass1.sh
#
# Resumable only for an identical build identity. Each configured build and
# installed prefix carries a content-derived stamp; a changed source, sysroot,
# host toolchain, configure contract, flag set, or cross-binutils install stops
# with an explicit request for a fresh build directory instead of silently
# reusing stale configure output.

set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) # pkgs/org.gnu.gcc/_cross
GCC_DIR=$(dirname "$SCRIPT_DIR")                           # pkgs/org.gnu.gcc
PKGS_DIR=$(dirname "$GCC_DIR")                             # pkgs

TARGET=x86_64-linux-peios
SYSROOT="$GCC_DIR/_sysroot"
CROSS="$SCRIPT_DIR/tools"
BUILD="$SCRIPT_DIR/build"
PATCH="$SCRIPT_DIR/config-sub-peios.sh"

command -v sha256sum >/dev/null || {
	echo "cross: sha256sum is required for build-identity validation" >&2
	exit 1
}

hash_tree()
{
	tree=$1
	paths=$(mktemp "${TMPDIR:-/tmp}/peios-cross-paths.XXXXXX")
	manifest=$(mktemp "${TMPDIR:-/tmp}/peios-cross-manifest.XXXXXX")
	(
		cd "$tree"
		find . \( -type d -o -type f -o -type l \) -print > "$paths"
		LC_ALL=C sort "$paths" | while IFS= read -r path; do
			mode=$(stat -c '%a' -- "$path")
			if [ -L "$path" ]; then
				printf 'L\t%s\t%s\t%s\n' "$mode" "$path" "$(readlink -- "$path")"
			elif [ -d "$path" ]; then
				printf 'D\t%s\t%s\n' "$mode" "$path"
			else
				printf 'F\t%s\t%s\t' "$mode" "$path"
				sha256sum -- "$path"
			fi
		done > "$manifest"
	)
	sha256sum "$manifest" | awk '{print $1}'
	rm -f "$paths" "$manifest"
}

command_identity()
{
	for name in cc c++ make ar as ld nm ranlib; do
		path=$(command -v "$name") || {
			echo "cross: required host tool not found: $name" >&2
			return 1
		}
		resolved=$(readlink -f "$path")
		printf '%s\t%s\t%s\t' "$name" "$path" "$resolved"
		sha256sum "$resolved"
	done
}

hash_identity()
{
	sha256sum | awk '{print $1}'
}

validate_build_identity()
{
	dir=$1
	expected=$2
	label=$3
	stamp="$dir/.peios-build-identity"
	if [ -f "$dir/Makefile" ]; then
		[ -f "$stamp" ] || {
			echo "cross: $label build cache has no identity stamp; move it aside and configure cleanly: $dir" >&2
			return 1
		}
		[ "$(cat "$stamp")" = "$expected" ] || {
			echo "cross: $label build identity changed; move the stale build directory aside: $dir" >&2
			return 1
		}
	elif [ -n "$(find "$dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
		echo "cross: $label has an incomplete unstamped build directory; move it aside: $dir" >&2
		return 1
	fi
}

validate_prefix_identity()
{
	stamp=$1
	expected=$2
	label=$3
	shift 3
	present=no
	for path in "$@"; do
		if [ -e "$path" ] || [ -L "$path" ]; then present=yes; fi
	done
	if [ "$present" = yes ]; then
		[ -f "$stamp" ] || {
			echo "cross: installed $label has no identity stamp; use a fresh cross prefix: $CROSS" >&2
			return 1
		}
		[ "$(cat "$stamp")" = "$expected" ] || {
			echo "cross: installed $label identity changed; use a fresh cross prefix: $CROSS" >&2
			return 1
		}
	fi
}

locked_source()
{
	recipe_dir=$1
	archive_stem=$2
	locked_version=$(awk -F '"' '/^[[:space:]]*version = "/ { version=$2 } END { print version }' "$recipe_dir/pekit.lock")
	[ -n "$locked_version" ] || {
		echo "cross: no locked version in $recipe_dir/pekit.lock" >&2
		return 1
	}
	found=
	for metadata in "$recipe_dir"/out/*/source.pekit.json; do
		[ -f "$metadata" ] || continue
		if grep -Fq "/$archive_stem-$locked_version" "$metadata"; then
			candidate=${metadata%/source.pekit.json}/source/
			[ -z "$found" ] || {
				echo "cross: multiple materialised sources match locked $archive_stem $locked_version" >&2
				return 1
			}
			found=$candidate
		fi
	done
	[ -n "$found" ] || {
		echo "cross: locked $archive_stem $locked_version is not materialised; run pekit build source --version $locked_version in $recipe_dir" >&2
		return 1
	}
	printf '%s\n' "$found"
}

BU_SRC=$(locked_source "$PKGS_DIR/org.gnu.binutils" binutils)
GCC_SRC=$(locked_source "$PKGS_DIR/org.gnu.gcc" gcc)

[ -n "$BU_SRC" ] && [ -f "$BU_SRC/configure" ] || { echo "cross: binutils source not fetched (run pekit build in pkgs/org.gnu.binutils)" >&2; exit 1; }
[ -n "$GCC_SRC" ] && [ -f "$GCC_SRC/configure" ] || { echo "cross: GCC source not fetched (run pekit build in pkgs/org.gnu.gcc)" >&2; exit 1; }
[ -f "$SYSROOT/usr/include/stdio.h" ] || { echo "cross: sysroot not composed at $SYSROOT (see header)" >&2; exit 1; }
[ -f "$SYSROOT/usr/lib/$TARGET/crti.o" ] || { echo "cross: sysroot missing crt objects at usr/lib/$TARGET" >&2; exit 1; }

# Hash complete materialised inputs rather than directory names or mtimes. The
# Canadian cross is infrequent and correctness here matters more than the few
# minutes needed to fingerprint a sysroot.
SYSROOT_ID=$(hash_tree "$SYSROOT")
for tool in cc c++ make ar as ld nm ranlib; do
	command -v "$tool" >/dev/null || {
		echo "cross: required host tool not found: $tool" >&2
		exit 1
	}
done
HOST_TOOLS_ID=$(command_identity | hash_identity)
ENV_FLAGS_ID=$(printf '%s\n' \
	"CFLAGS=${CFLAGS-}" "CXXFLAGS=${CXXFLAGS-}" "CPPFLAGS=${CPPFLAGS-}" \
	"LDFLAGS=${LDFLAGS-}" "CC=${CC-}" "CXX=${CXX-}" "PATH=${PATH-}" | hash_identity)

# Memory-bounded parallelism aligned with the native recipe: use available
# memory, reserve 6 GiB for the compositor/other work, and never exceed four
# jobs.
JOBS=$(nproc)
AVAILABLE_KIB=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
if [ "$AVAILABLE_KIB" -gt 6000000 ]; then
	MEMJOBS=$(( (AVAILABLE_KIB - 6000000) / 2000000 ))
else
	MEMJOBS=1
fi
[ "$MEMJOBS" -lt "$JOBS" ] && JOBS=$MEMJOBS
[ "$JOBS" -gt 4 ] && JOBS=4
[ "$JOBS" -lt 1 ] && JOBS=1

export PATH="$CROSS/bin:$PATH"

echo "cross: target=$TARGET jobs=$JOBS"
echo "cross: sysroot=$SYSROOT"
echo "cross: prefix=$CROSS"
echo "cross: binutils=$BU_SRC"
echo "cross: gcc=$GCC_SRC"

# ---------------------------------------------------------------------------
# Pass 1a: cross binutils (as/ld/ar for the peios target, run on Debian).
# config.sub learns peios; no multiarch concern here — gcc passes ld the -L
# search dirs, so ld needs only --with-sysroot for the default prefix.
# ---------------------------------------------------------------------------
echo "=== cross-binutils ==="
sh "$PATCH" "$BU_SRC/config.sub"
# config.sub is an intentional source edit, so include its post-edit content.
BU_SOURCE_ID=$(hash_tree "$BU_SRC")
BU_CONFIG_ID=$(printf '%s\n' \
	"schema=peios-cross-binutils-v1" \
	"source-path=$BU_SRC" "source=$BU_SOURCE_ID" \
	"sysroot-path=$SYSROOT" "sysroot=$SYSROOT_ID" \
	"host-tools=$HOST_TOOLS_ID" "env-flags=$ENV_FLAGS_ID" \
	"prefix=$CROSS" "target=$TARGET" \
	"configure=--prefix=PREFIX --target=TARGET --with-sysroot=SYSROOT --disable-nls --disable-werror --enable-deterministic-archives --enable-plugins --with-system-zlib" | hash_identity)
mkdir -p "$BUILD/binutils"
validate_build_identity "$BUILD/binutils" "$BU_CONFIG_ID" binutils
validate_prefix_identity "$CROSS/.peios-binutils-identity" "$BU_CONFIG_ID" \
	binutils "$CROSS/bin/$TARGET-as" "$CROSS/bin/$TARGET-ld" \
	"$CROSS/bin/$TARGET-ar" "$CROSS/bin/$TARGET-nm" "$CROSS/bin/$TARGET-ranlib"
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
	printf '%s\n' "$BU_CONFIG_ID" > .peios-build-identity
fi
make -j"$JOBS"
make install
printf '%s\n' "$BU_CONFIG_ID" > "$CROSS/.peios-binutils-identity"

# GCC configure and build consume the installed cross assembler/linker rather
# than only the binutils source. Bind their exact executable payloads into the
# GCC identity so even an in-place binutils replacement invalidates reuse.

for tool in as ld ar nm ranlib; do
	path="$CROSS/bin/$TARGET-$tool"
	[ -x "$path" ] || { echo "cross: installed binutils lacks $path" >&2; exit 1; }
done
CROSS_BINUTILS_ID=$(
	for tool in as ld ar nm ranlib; do
		path="$CROSS/bin/$TARGET-$tool"
		printf '%s\t' "$tool"
		sha256sum "$path"
	done | hash_identity
)

# ---------------------------------------------------------------------------
# Pass 1b: cross gcc (C/C++) + peios target libgcc/libstdc++, against the
# existing sysroot glibc (so it builds in one pass — no glibc chicken/egg).
#
# Pekit's source materialisation has already applied the GCC patch series,
# including Peios identity, ELF/LTO handling, and the triplet multiarch paths.
# config.sub remains version-sensitive and is taught Peios by the helper here.
# Assert the materialised source has the non-generated patches as well, so a
# hand-populated source tree cannot silently produce a generic or non-LTO GCC.
# ---------------------------------------------------------------------------
echo "=== cross-gcc ==="
sh "$PATCH" "$GCC_SRC/config.sub"
grep -q 'x86_64-linux-peios' "$GCC_SRC/gcc/config/i386/t-linux64" || {
	echo "cross: GCC source is missing the Peios multiarch patch" >&2
	exit 1
}
[ -f "$GCC_SRC/gcc/config/linux-peios.h" ] || {
	echo "cross: GCC source is missing the Peios target-identity patch" >&2
	exit 1
}
grep -q '\*-linux-peios\*)' "$GCC_SRC/config/elf.m4" || {
	echo "cross: GCC source is missing the Peios ELF/LTO patch" >&2
	exit 1
}
GCC_SOURCE_ID=$(hash_tree "$GCC_SRC")
GCC_CONFIG_ID=$(printf '%s\n' \
	"schema=peios-cross-gcc-v1" \
	"source-path=$GCC_SRC" "source=$GCC_SOURCE_ID" \
	"sysroot-path=$SYSROOT" "sysroot=$SYSROOT_ID" \
	"host-tools=$HOST_TOOLS_ID" "env-flags=$ENV_FLAGS_ID" \
	"binutils-config=$BU_CONFIG_ID" "binutils-payload=$CROSS_BINUTILS_ID" \
	"prefix=$CROSS" "target=$TARGET" \
	"configure=--prefix=PREFIX --target=TARGET --with-sysroot=SYSROOT --disable-multilib --disable-bootstrap --enable-languages=c,c++ --enable-shared --enable-threads=posix --enable-__cxa_atexit --disable-libsanitizer --disable-werror" | hash_identity)
mkdir -p "$BUILD/gcc"
validate_build_identity "$BUILD/gcc" "$GCC_CONFIG_ID" gcc
validate_prefix_identity "$CROSS/.peios-gcc-identity" "$GCC_CONFIG_ID" \
	gcc "$CROSS/bin/$TARGET-gcc" "$CROSS/bin/$TARGET-g++" \
	"$CROSS/bin/$TARGET-cpp"
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
	printf '%s\n' "$GCC_CONFIG_ID" > .peios-build-identity
fi
make -j"$JOBS"
make install
printf '%s\n' "$GCC_CONFIG_ID" > "$CROSS/.peios-gcc-identity"

echo
echo "cross: DONE. Toolchain at $CROSS/bin (prefix $TARGET-)"
echo "cross: verify with  sh $SCRIPT_DIR/verify-cross.sh"
