#!/bin/sh
# Host-compatible installed binary gate; FACS cases run in test-facs.sh.
set -eu
nano=$1
pty=$2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cd "$work"
export TERM=xterm LC_ALL=C
"$nano" --version | grep -F "${PEKIT_VERSION:-9.2}"
printf 'original\n' > document
ln document hardlink
cat > edit.script <<'EOF'
expect original
send added\r
send \x0f
expect Write to File
send \r
expect Wrote
send \x18
EOF
"$pty" edit.script -- "$nano" --ignorercfiles document
printf 'added\noriginal\n' > expected
cmp expected document
cmp expected hardlink
cat > new.script <<'EOF'
expect New Buffer
send new document
send \x0f
expect Write to File
send newfile\r
expect Wrote
send \x18
EOF
"$pty" new.script -- "$nano" --ignorercfiles
printf 'new document\n' > expected
cmp expected newfile
printf '%s\n' 'nano installed editing checks passed'
