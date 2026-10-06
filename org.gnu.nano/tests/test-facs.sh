#!/bin/sh
# Disposable guest test. Arguments are explicit, qualified build inputs:
# KERNEL NANO_STAGE NANO_SOURCE LIBPEIOS_CHECKOUT PKM_UAPI RUNTIME_ROOT
set -eu
[ "$#" = 6 ] || { echo "usage: $0 KERNEL NANO_STAGE NANO_SOURCE LIBPEIOS_CHECKOUT PKM_UAPI RUNTIME_ROOT" >&2; exit 2; }
kernel=$(realpath "$1")
stage=$(realpath "$2")
source=$(realpath "$3")
libpeios=$(realpath "$4")
uapi=$(realpath "$5")
runtime=$(realpath "$6")
tests=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
mkdir -p "$work/root/lib64" "$work/root/lib" "$work/root/usr/lib/x86_64-linux-peios" "$work/root/usr/share"
# The no_std archive provides an unused unwind abort stub; glibc's static
# unwinder also defines it. This exception is confined to the VM harness.
cc -static -O2 -Wall -Wextra -Werror -DENABLE_PEIOS \
  -I"$source/src" -I"$libpeios/include" -I"$uapi" \
  "$tests/facs.c" "$source/src/peios.c" "$libpeios/target/release/libpeios.a" \
  -Wl,--allow-multiple-definition -ldl -lpthread -lm -o "$work/root/init"
cp "$stage/usr/bin/nano" "$work/root/nano"
libdir="$runtime/usr/lib/x86_64-linux-peios"
cp -L "$libdir/ld-linux-x86-64.so.2" "$work/root/lib64/"
for lib in libpeios.so.0 libncursesw.so.6 libtinfo.so.6 libc.so.6; do
  cp -L "$libdir/$lib" "$work/root/usr/lib/x86_64-linux-peios/"
done
cp -a "$runtime/usr/share/terminfo" "$work/root/usr/share/"
(cd "$work/root" && find . -print0 | cpio --null -o --format=newc --quiet) > "$work/initrd"
log=${NANO_FACS_LOG:-nano-facs.log}
timeout 90s "${QEMU_BIN:-qemu-system-x86_64}" -m 1024 -smp 2 -nographic -no-reboot \
  -serial mon:stdio -machine accel=kvm:tcg -cpu max -kernel "$kernel" -initrd "$work/initrd" \
  -append 'console=ttyS0 quiet loglevel=4 panic=-1 kunit.enable=0 rdinit=/init' > "$log" 2>&1
if ! grep -F 'NANO_FACS_PASS:' "$log" || grep -Eq 'NANO_FACS_FAIL:|Kernel panic|BUG:|Oops:' "$log"; then
  tail -40 "$log"
  exit 1
fi
