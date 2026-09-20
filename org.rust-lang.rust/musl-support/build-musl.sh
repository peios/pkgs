set -eu
SRC="$(pwd -P)"
BUILD="$PEKIT_OUT/build"
PREFIX=/usr/lib/x86_64-linux-peios/musl
STAGE="$PEKIT_OUT$PREFIX"

# musl 1.2.6 predates the upstream fix for CVE-2026-6042. Apply the exact
# upstream commit while the vulnerable decoder is present; the postcondition
# lets a future 1.2 release which already contains it update unattended.
if ! grep -q '#include "gb18030utf.h"' "$SRC/src/locale/iconv.c"; then
  python3 - "$SRC" \
    "$PEKIT_RECIPE_ROOT/patches/0001-fix-cve-2026-6042-gb18030-dos.patch" <<'PY'
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1])
patch_text = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")

# Materialize the new table directly from the signed-off upstream patch.
table_diff, iconv_diff = patch_text.split(
    "diff --git a/src/locale/iconv.c b/src/locale/iconv.c", 1
)
table_hunk = table_diff.split("@@ -0,0 +1,206 @@\n", 1)[1]
table_lines = [line[1:] for line in table_hunk.splitlines(keepends=True)
               if line.startswith("+") and not line.startswith("+++")]
if len(table_lines) != 206:
    raise SystemExit("musl: upstream GB18030 table patch is malformed")
(source / "src/locale/gb18030utf.h").write_text(
    "".join(table_lines), encoding="utf-8"
)

# Apply each iconv hunk with exact context and no fuzz. This small strict
# parser exists because Peios does not yet package the standalone patch tool.
target = source / "src/locale/iconv.c"
original = target.read_text(encoding="utf-8").splitlines(keepends=True)
hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$", re.M)
matches = list(hunk_re.finditer(iconv_diff))
if len(matches) != 3:
    raise SystemExit("musl: unexpected iconv security-patch hunk count")
result = []
cursor = 0
for index, match in enumerate(matches):
    old_start = int(match.group(1)) - 1
    old_count = int(match.group(2) or "1")
    new_count = int(match.group(4) or "1")
    result.extend(original[cursor:old_start])
    cursor = old_start
    old_seen = new_seen = 0
    body_end = matches[index + 1].start() if index + 1 < len(matches) else len(iconv_diff)
    body = iconv_diff[match.end():body_end].lstrip("\n")
    for line in body.splitlines(keepends=True):
        if old_seen == old_count and new_seen == new_count:
            break
        if not line or line[0] not in " +-":
            raise SystemExit("musl: malformed iconv security-patch hunk")
        marker, payload = line[0], line[1:]
        if marker in " -":
            if cursor >= len(original) or original[cursor] != payload:
                raise SystemExit("musl: iconv security patch context drifted")
            cursor += 1
            old_seen += 1
        if marker in " +":
            result.append(payload)
            new_seen += 1
    if old_seen != old_count or new_seen != new_count:
        raise SystemExit("musl: incomplete iconv security-patch hunk")
result.extend(original[cursor:])
target.write_text("".join(result), encoding="utf-8")
PY
fi
grep -q '#include "gb18030utf.h"' "$SRC/src/locale/iconv.c"
test -s "$SRC/src/locale/gb18030utf.h"

mkdir -p "$BUILD"
cd "$BUILD"

# The compiler is a Peios-native GCC, but the produced ABI is musl. Setting
# the target gives musl the canonical architecture while CROSS_COMPILE= on
# make deliberately selects the native binutils already in the build root.
export CFLAGS="${CFLAGS:--O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=3} -fcf-protection=full -ffile-prefix-map=$SRC=/usr/src/debug/org.libc.musl-sysroot/source"
export LDFLAGS="${LDFLAGS:-} -Wl,-z,relro,-z,now -Wl,--as-needed -Wl,-z,pack-relative-relocs -Wl,-z,ibtplt"
CC=cc "$SRC/configure" \
  --target=x86_64-linux-musl \
  --prefix="$PREFIX" \
  --syslibdir="$PREFIX/lib" \
  --disable-wrapper \
  --disable-shared

make CROSS_COMPILE= -j"$(nproc)"
make CROSS_COMPILE= install DESTDIR="$PEKIT_OUT"
