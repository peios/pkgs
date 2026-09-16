set -eu

PKM_REV=b5519e6da3ecd4ce854c6299af6844f0a6ce05dd
PKM_SHORT=$(printf %.7s "$PKM_REV")
export CARGO_HOME=/tmp/cargo-libpeios-vendor
mkdir -p "$CARGO_HOME" "$PEKIT_OUT"

grep -F "pkm.git?rev=$PKM_REV#$PKM_REV" Cargo.lock >/dev/null
cargo vendor --locked "$PEKIT_OUT/vendor" > "$PEKIT_OUT/cargo-config.toml"
test -s "$PEKIT_OUT/cargo-config.toml"
test -n "$(find "$PEKIT_OUT/vendor" -mindepth 1 -maxdepth 1 -type d -print -quit)"

# cargo vendor copies only the selected crates. libpeios's public C headers also
# include <pkm/*.h>, which live beside those crates in the same locked PKM Git
# checkout. Preserve that exact checkout's userspace UAPI as a build input.
PKM_ROOT=
for candidate in "$CARGO_HOME"/git/checkouts/pkm-*/*; do
  [ -d "$candidate/uapi/pkm" ] || continue
  [ "$(basename "$candidate")" = "$PKM_SHORT" ] || continue
  [ -z "$PKM_ROOT" ] || { echo "multiple PKM checkouts match $PKM_REV" >&2; exit 1; }
  PKM_ROOT=$candidate
done
test -n "$PKM_ROOT" || { echo "Cargo did not materialize locked PKM checkout $PKM_REV" >&2; exit 1; }
cp -R "$PKM_ROOT/uapi" "$PEKIT_OUT/pkm-uapi"
test -f "$PEKIT_OUT/pkm-uapi/pkm/pkm.h"
