#!/bin/sh
# List the production microcode files the early-load blob is assembled from,
# one path per line in LC_ALL=C order. The build concatenates exactly this
# list and the gate re-derives it, so both share one selection rule.
#
#   list-intel-ucode.sh SOURCE-ROOT
#
# Only intel-ucode/ is production data (intel-ucode-with-caveats/ is not), and
# every file in it must be named family-model-stepping in hex: an unexpected
# name fails rather than being silently left out.
set -eu

[ $# -eq 1 ] || { echo "usage: list-intel-ucode.sh SOURCE-ROOT" >&2; exit 2; }
DIR="$1/intel-ucode"
HEX='[0123456789abcdefABCDEF][0123456789abcdefABCDEF]'
LIST=$(find "$DIR" -maxdepth 1 -type f -name "$HEX-$HEX-$HEX" -print | LC_ALL=C sort)
if [ -z "$LIST" ]; then
  echo "intel-ucode: no production microcode files in $DIR" >&2
  exit 1
fi
if [ "$(printf '%s\n' "$LIST" | wc -l)" -ne \
     "$(find "$DIR" -maxdepth 1 -type f -print | wc -l)" ]; then
  echo "intel-ucode: a production microcode file in $DIR has an unexpected name" >&2
  exit 1
fi
printf '%s\n' "$LIST"
