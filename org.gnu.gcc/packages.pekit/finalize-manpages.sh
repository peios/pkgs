#!/bin/sh
# Idempotent post-install documentation step; never touches compiler outputs.
set -eu
: "${PEKIT_OUT:?}" "${PEKIT_RECIPE_ROOT:?}" "${PEKIT_VERSION:?}"
triplet=x86_64-linux-peios
major=${PEKIT_VERSION%%.*}
manroot=$PEKIT_OUT/usr/share/man
test -d "$manroot/man1"
# Overwrite our own generated compressed manual deterministically on reruns.
gzip -n -9 -c "$PEKIT_RECIPE_ROOT/packages.pekit/gcc-ar.1" > "$manroot/man1/gcc-ar.1.gz"
find "$manroot" -type f ! -name '*.gz' -exec gzip -n -9 -- {} +
cd "$manroot/man1"
for page in gcc g++ cpp gcov gcov-dump gcov-tool lto-dump gcc-ar; do
  gzip -t "$page.1.gz"
done
for alias in cc "$triplet-gcc" "$triplet-gcc-$major"; do
  ln -sfn gcc.1.gz "$alias.1.gz"
done
for alias in c++ "$triplet-c++" "$triplet-g++"; do
  ln -sfn g++.1.gz "$alias.1.gz"
done
for alias in gcc-nm gcc-ranlib "$triplet-gcc-ar" "$triplet-gcc-nm" "$triplet-gcc-ranlib"; do
  ln -sfn gcc-ar.1.gz "$alias.1.gz"
done
