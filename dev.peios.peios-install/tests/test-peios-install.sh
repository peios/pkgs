#!/usr/bin/sh
set -eu

ROOT=$(mktemp -d "${TMPDIR:-/tmp}/peios-install-test.XXXXXX")
trap 'rm -rf "$ROOT"' EXIT INT TERM
mkdir -p "$ROOT/bin"

cat > "$ROOT/partitions" <<'EOF'
major minor  #blocks  name

 252        0    8388608 vdb
 252        1     524288 vdb1
 252        2    7863296 vdb2
 259        0    8388608 nvme0n1
 259        1     524288 nvme0n1p1
EOF

cat > "$ROOT/mounts" <<'EOF'
/dev/root / ext4 rw 0 0
/dev/vdb1 /boot vfat rw 0 0
proc /proc proc rw 0 0
EOF

cat > "$ROOT/bin/part" <<'EOF'
#!/usr/bin/sh
printf '%s\n' "$*" > "$PART_ARGS"
exit "$PART_STATUS"
EOF
mkexec "$ROOT/bin/part"

PEIOS_INSTALL_LIBRARY_ONLY=1
PEIOS_INSTALL_PROC_PARTITIONS="$ROOT/partitions"
PEIOS_INSTALL_PROC_MOUNTS="$ROOT/mounts"
export PEIOS_INSTALL_LIBRARY_ONLY PEIOS_INSTALL_PROC_PARTITIONS PEIOS_INSTALL_PROC_MOUNTS
. ./src/peios-install.sh

is_block_device /dev/vdb
is_block_device /dev/nvme0n1p1
for not_block in /dev/missing /dev/ /dev/disk/by-id/example; do
    if is_block_device "$not_block"; then
        echo "peios-install test: $not_block accepted as a block device" >&2
        exit 1
    fi
done

is_mounted_device /dev/vdb1
if is_mounted_device /dev/vdb2; then
    echo "peios-install test: /dev/vdb2 reported as mounted" >&2
    exit 1
fi

PATH="$ROOT/bin:$PATH"
PART_ARGS="$ROOT/part.args"
export PATH PART_ARGS

PART_STATUS=0
export PART_STATUS
create_partition_table /dev/vdb ''
[ "$(cat "$PART_ARGS")" = 'create /dev/vdb --yes' ]

create_partition_table /dev/vdb --force
[ "$(cat "$PART_ARGS")" = 'create /dev/vdb --yes --force' ]

PART_STATUS=3
export PART_STATUS
if message=$(create_partition_table /dev/vdb '' 2>&1); then
    echo 'expected a refusal to fail' >&2
    exit 1
fi
case "$message" in
    *'carries a partition table part will not replace'*'pass --force'*) ;;
    *) echo "wrong refusal diagnostic: $message" >&2; exit 1 ;;
esac

PART_STATUS=1
export PART_STATUS
if message=$(create_partition_table /dev/vdb '' 2>&1); then
    echo 'expected a partitioning failure to fail' >&2
    exit 1
fi
case "$message" in
    *'could not write a partition table'*) ;;
    *) echo "wrong failure diagnostic: $message" >&2; exit 1 ;;
esac

printf '%s\n' 'peios-install tests: PASS'
