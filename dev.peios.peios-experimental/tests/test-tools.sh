#!/bin/sh
# Run inside a freshly composed system root, with a writable TMPDIR.
# Exercises runtime package closure: build dependencies must not supply tools.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cd "$work"
for tool in grep sed awk find xargs diff cmp tar gzip xz zstd bzip2 file less zip unzip zipinfo nano; do
    command -v "$tool" >/dev/null
done
printf 'alpha 1\nbeta 2\n' > input
[ "$(grep -P -o '(?<=beta )\d+' input)" = 2 ]
[ "$(sed -n 's/beta /value=/p' input)" = value=2 ]
[ "$(awk '{sum += $2} END {print sum}' input)" = 3 ]
cp input same
cmp input same
diff input same
mkdir files
cp input 'files/two words.txt'
find files -type f -print0 | xargs -0 cat > selected
cmp input selected
file input | grep -F 'text'
less input > paged
cmp input paged
for suffix in gz xz zst bz2; do
    tar -caf "archive.tar.$suffix" files
    tar -tf "archive.tar.$suffix" | grep -F 'files/two words.txt'
    mkdir "restored-$suffix"
    tar -xf "archive.tar.$suffix" -C "restored-$suffix"
    cmp input "restored-$suffix/files/two words.txt"
done
zip -qr archive.zip files
unzip -t archive.zip
zipinfo -1 archive.zip | grep -Fx 'files/two words.txt'
unzip -q archive.zip -d restored-zip
cmp input 'restored-zip/files/two words.txt'
nano --version | grep -F 'GNU nano'
printf '%s\n' 'Experimental text/archive/editor runtime checks passed'
