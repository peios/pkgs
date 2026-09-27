#!/bin/sh
set -eu
stage=$PEKIT_MAIN_OUT
bin=$stage/usr/bin
work=$PEKIT_OUT/installed
mkdir -p "$work"
"$bin/loadkeys" --version | grep -F "$PEKIT_VERSION"
test ! -e "$bin/vlock"
test ! -e "$stage/etc/pam.d"
test -L "$bin/psfgettable"
test -L "$bin/psfstriptable"

# Parse the installed keymaps and their includes without changing a console.
export LOADKEYS_INCLUDE_PATH="$stage/usr/share/kbd/keymaps/**"
export LOADKEYS_KEYMAP_PATH="$stage/usr/share/kbd/keymaps/**"
for layout in us uk de fr; do
  "$bin/loadkeys" --bkeymap "$layout" > "$work/$layout.bmap"
  test -s "$work/$layout.bmap"
done
if cmp -s "$work/us.bmap" "$work/uk.bmap"; then exit 1; fi
printf 'keycode invalid = broken\n' > "$work/invalid.map"
if "$bin/loadkeys" --bkeymap "$work/invalid.map" > /dev/null 2>&1; then exit 1; fi

# Exercise the shipped font reader/writer and symlink command dispatch.
gzip -dc "$stage/usr/share/kbd/consolefonts/Lat2-Terminus16.psfu.gz" > "$work/font.psf"
"$bin/psfgettable" "$work/font.psf" "$work/font.table"
test -s "$work/font.table"
"$bin/psfstriptable" "$work/font.psf" "$work/stripped.psf"
"$bin/psfaddtable" "$work/stripped.psf" "$work/font.table" "$work/restored.psf"
"$bin/psfgettable" "$work/restored.psf" "$work/restored.table"
cmp "$work/font.table" "$work/restored.table"

for tool in loadkeys dumpkeys setfont chvt openvt; do
  readelf -h "$bin/$tool" | grep -E 'Type:[[:space:]]+DYN'
  readelf -d "$bin/$tool" | grep -F BIND_NOW
  readelf -n "$bin/$tool" | grep -E 'x86 feature:.*IBT.*SHSTK'
done
test -n "$(find "$stage/usr/lib/debug/.build-id" -name '*.debug' -print -quit)"
test -n "$(find "$stage/usr/src/debug/org.kernel.kbd" -type f -print -quit)"
echo KBD_INSTALLED_CHECKS_PASSED
