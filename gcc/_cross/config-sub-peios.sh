#!/bin/sh
# Teach a GNU config.sub about the `peios` userland so configure accepts the
# x86_64-linux-peios triplet (kernel=linux, os/userland=peios). Same model as
# `android`: the final field is the userland; the kernel stays `linux`.
#
# Idempotent: a config.sub that already knows peios is left untouched. Operates
# on the file given as $1 (defaults to ./config.sub).
#
# Two config.sub vintages ship in the toolchain, handled separately:
#
#   NEW, obj-aware layout (binutils 2.46.1 — has a `case $obj in` block). Three
#   surgical edits:
#     1. OS-normalization `case $os in`: insert a `peios*)` no-op arm BEFORE the
#        `aout* | coff* | elf* | pe*)` machine-code-format arm. Without it the
#        `pe*` glob captures "peios" and mis-normalizes it to obj=peios, os=''.
#        First occurrence ONLY (`0,/re/`): the second identical line is the
#        `case $obj in` VALIDATOR and must stay peios-free.
#     2. Valid-OS accept-list: register `peios*` alongside `android*`.
#     3. Kernel-OS combination allowlist (`case $kernel-$os-$obj`): register
#        `linux-peios*-` alongside `linux-android*-`.
#
#   OLD layout (gcc 16.1.0 — no `case $obj`). Its OS accept-list already admits
#   peios via the `pe*` glob, and it has no obj normalizer, so only ONE edit:
#     - Kernel-OS combination allowlist (`case $kernel-$os`): register
#       `linux-peios*` alongside `linux-gnu*`.

set -eu

f="${1:-config.sub}"

[ -f "$f" ] || { echo "config-sub-peios: $f not found" >&2; exit 1; }

if grep -q 'peios' "$f"; then
	echo "config-sub-peios: $f already knows peios — skipping"
	exit 0
fi

# require <regex> <human-label>: fail the build loudly if an edit silently
# missed (e.g. a future upstream reshuffle) instead of regressing the triplet.
require() {
	grep -qE "$1" "$f" || {
		echo "config-sub-peios: $2 did not apply to $f" >&2
		exit 1
	}
}

if grep -q '^case \$obj in' "$f"; then
	# NEW obj-aware layout.
	sed -i '0,/^\taout\* | coff\* | elf\* | pe\*)/ s//\tpeios*)\n\t\t;;\n&/' "$f"
	sed -i 's@^\t| android\* \\@&\n\t| peios* \\@' "$f"
	sed -i 's@linux-android\*- @&| linux-peios*- @' "$f"
	require '^[[:space:]]*peios\*\)' 'OS normalizer arm'
	require '\| peios\* '            'OS accept-list entry'
	require 'linux-peios\*- '        'kernel-OS combination'
else
	# OLD layout: kernel-os combination only (pe* already accepts the OS).
	sed -i 's@^\tlinux-gnu\* | linux-dietlibc\* @\tlinux-peios* | linux-gnu* | linux-dietlibc* @' "$f"
	require 'linux-peios\* '        'kernel-OS combination'
fi

echo "config-sub-peios: patched $f"
