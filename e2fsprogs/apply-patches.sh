#!/usr/bin/env bash
# Apply the Peios e2fsprogs patch series to an e2fsprogs source tree.
#
# Each patch is a plain unified diff against the pinned e2fsprogs version
# ($E2FSPROGS_VERSION); the `series` file lists them in apply order. A patch
# either applies cleanly or fails loudly. On a version bump, re-run with
# E2FSPROGS_PATCH_3WAY=1 to fall back to a 3-way merge and surface conflicts
# as ordinary .rej / <<< markers.
#
# usage: apply-patches.sh <e2fsprogs-tree> [patches-dir]
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
	echo "usage: $0 <e2fsprogs-tree> [patches-dir]" >&2
	exit 2
fi

tree=$(cd "$1" 2>/dev/null && pwd) || { echo "no such e2fsprogs tree: $1" >&2; exit 1; }
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patches=${2:-$here/patches}
patches=$(cd "$patches" 2>/dev/null && pwd) || { echo "no such patches dir: ${2:-}" >&2; exit 1; }

[[ -f "$patches/series" ]] || { echo "no series file in: $patches" >&2; exit 1; }

# --- guard: $tree must be an e2fsprogs source root, not a wrapper dir ---
# Catches pointing at a parent dir that merely *contains* the tree. configure.ac
# + lib/ext2fs/ext2fs.h are the e2fsprogs analogue of the kernel's
# Makefile + security/security.c root markers.
if [[ ! -f "$tree/configure.ac" ]] || [[ ! -f "$tree/lib/ext2fs/ext2fs.h" ]]; then
	echo "not an e2fsprogs source root (no configure.ac / lib/ext2fs/ext2fs.h): $tree" >&2
	echo "  hint: pass the tree root itself, not a directory that contains it" >&2
	exit 1
fi

# --- defeat stray parent-repo resolution ---
# `git apply` inside SOME git repo treats patches whose target paths are
# absent/untracked as "Skipped" and STILL exits 0. If $tree is not its own git
# root, git walks up to an unrelated ancestor and silently skips every patch.
# Stop the upward search at $tree's parent.
export GIT_CEILING_DIRECTORIES
GIT_CEILING_DIRECTORIES=$(dirname "$tree")

apply_flags=(--whitespace=nowarn)
if [[ "${E2FSPROGS_PATCH_3WAY:-0}" == "1" ]]; then
	apply_flags+=(--3way)
fi

count=0
while IFS= read -r entry || [[ -n "$entry" ]]; do
	entry=${entry%%#*}                       # strip comments
	entry=$(printf '%s' "$entry" | tr -d '[:space:]')
	[[ -z "$entry" ]] && continue
	patch="$patches/$entry"
	[[ -f "$patch" ]] || { echo "missing patch in series: $entry" >&2; exit 1; }

	# A skip prints "Skipped patch" and exits 0 — treat as failure.
	out=$(git -C "$tree" apply "${apply_flags[@]}" "$patch" 2>&1) || {
		[[ -n "$out" ]] && echo "$out" >&2
		echo "FAILED to apply: $entry" >&2
		exit 1
	}
	if grep -q 'Skipped patch' <<<"$out"; then
		echo "$out" >&2
		echo "SKIPPED (target not found / not applied): $entry" >&2
		exit 1
	fi
	count=$((count + 1))
done < "$patches/series"

echo "apply-patches: applied $count patches cleanly into $tree"
