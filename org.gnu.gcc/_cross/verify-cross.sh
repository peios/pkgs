#!/bin/sh
# Smoke-test the Pass-1 cross-toolchain: compile a C and a C++ program for the
# peios target, confirm they are correct x86_64 ELFs with the standard loader,
# and actually RUN them through the sysroot loader. Invoking that loader
# explicitly proves the programs use the composed Peios runtime rather than
# whichever compatible glibc happens to be installed on the Debian build host.
#
#   sh pkgs/org.gnu.gcc/_cross/verify-cross.sh

set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
GCC_DIR=$(dirname "$SCRIPT_DIR")

TARGET=x86_64-linux-peios
SYSROOT="$GCC_DIR/_sysroot"
CROSS="$SCRIPT_DIR/tools"
export PATH="$CROSS/bin:$PATH"

LOADER="$SYSROOT/usr/lib/$TARGET/ld-linux-x86-64.so.2"
# Run-time search: sysroot libs + wherever the cross installed target libstdc++.
CXXLIB=$(dirname "$("$TARGET-gcc" -print-file-name=libstdc++.so.6)")
LIBPATH="$SYSROOT/usr/lib/$TARGET:$CXXLIB"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

printf '#include <stdio.h>\nint main(void){puts("hello from peios (C)");return 0;}\n' > "$tmp/h.c"
printf '#include <iostream>\nint main(){std::cout<<"hello from peios (C++)\\n";}\n' > "$tmp/h.cc"

echo "=== toolchain identity ==="
echo "-dumpmachine : $("$TARGET-gcc" -dumpmachine)"
echo "-print-multiarch: $("$TARGET-gcc" -print-multiarch)"
echo "libstdc++ dir: $CXXLIB"
echo

"$TARGET-gcc"  -O2 "$tmp/h.c"  -o "$tmp/h_c"
"$TARGET-g++"  -O2 "$tmp/h.cc" -o "$tmp/h_cpp"

rc=0
for b in "$tmp/h_c" "$tmp/h_cpp"; do
	echo "=== $(basename "$b") ==="
	readelf -h "$b" | grep -E 'Class|Machine|Type'
	interp=$(readelf -l "$b" | sed -n 's/.*interpreter: \(.*\)\]/\1/p')
	echo "interpreter : $interp"
	[ "$interp" = "/lib64/ld-linux-x86-64.so.2" ] || { echo "  !! expected /lib64/ld-linux-x86-64.so.2"; rc=1; }
	echo "NEEDED      : $(readelf -d "$b" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | tr '\n' ' ')"
	printf 'run         : '
	if "$LOADER" --library-path "$LIBPATH" "$b"; then :; else echo "  !! RUN FAILED"; rc=1; fi
	echo
done

[ $rc -eq 0 ] && echo "cross: VERIFY OK" || echo "cross: VERIFY FAILED"
exit $rc
