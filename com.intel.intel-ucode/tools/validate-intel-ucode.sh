#!/bin/sh
# Validate one or more Intel microcode containers using the format and checksum
# rules enforced by the Linux early microcode loader.
set -eu

VALIDATE_TMP=$(mktemp -d)
trap 'rm -rf "$VALIDATE_TMP"' EXIT HUP INT TERM
HEADER_TMP="$VALIDATE_TMP/header"
RECORD_TMP="$VALIDATE_TMP/record"

fail_microcode() {
  printf '%s\n' "intel microcode validation failed: $*" >&2
  exit 1
}

validate_checksum_region() {
  region_file="$1"
  region_offset="$2"
  region_size="$3"
  dd if="$region_file" of="$RECORD_TMP" bs=4 skip=$((region_offset / 4)) \
    count=$((region_size / 4)) status=none
  test "$(wc -c < "$RECORD_TMP")" -eq "$region_size" || return 1
  od -An -v -tu4 -w4 "$RECORD_TMP" \
    | awk '{ sum += $1; while (sum >= 4294967296) sum -= 4294967296 }
           END { exit(sum == 0 ? 0 : 1) }'
}

# Intel update files may contain multiple records. Validate each record's
# header, optional extended-signature table, declared sizes and little-endian
# 32-bit additive checksums. Current Intel data uses formerly-reserved main
# header words, so those words are intentionally left opaque, as Linux does.
validate_microcode_file() {
  file="$1"
  file_size="$(wc -c < "$file")"
  test "$file_size" -gt 0 || fail_microcode "$file is empty"
  test $((file_size % 4)) -eq 0 \
    || fail_microcode "$file is not a sequence of 32-bit words"

  offset=0
  records=0
  while test "$offset" -lt "$file_size"; do
    remaining=$((file_size - offset))
    test "$remaining" -ge 48 \
      || fail_microcode "$file has a truncated header at byte $offset"

    dd if="$file" of="$HEADER_TMP" bs=4 skip=$((offset / 4)) count=12 status=none
    set -- $(od -An -v -tu4 "$HEADER_TMP")
    test "$#" -eq 12 \
      || fail_microcode "$file has an unreadable header at byte $offset"

    header_version="$1"
    update_revision="$2"
    processor_signature="$4"
    main_checksum="$5"
    loader_revision="$6"
    processor_flags="$7"
    data_size="$8"
    total_size="$9"

    test "$header_version" -eq 1 \
      || fail_microcode "$file record at byte $offset has header version $header_version"
    test "$loader_revision" -eq 1 \
      || fail_microcode "$file record at byte $offset has loader revision $loader_revision"
    test "$update_revision" -ne 0 \
      || fail_microcode "$file record at byte $offset has revision zero"
    test "$processor_signature" -ne 0 \
      || fail_microcode "$file record at byte $offset has processor signature zero"
    if test "$data_size" -eq 0; then
      test "$total_size" -eq 0 \
        || fail_microcode "$file legacy record at byte $offset has an inconsistent total size"
      record_size=2048
      base_size=2048
      extension_size=0
    else
      test $((data_size % 4)) -eq 0 \
        || fail_microcode "$file record at byte $offset has an unaligned data size"
      test "$total_size" -ge $((48 + data_size)) \
        || fail_microcode "$file record at byte $offset is smaller than its data"
      test $((total_size % 1024)) -eq 0 \
        || fail_microcode "$file record at byte $offset is not 1-KiB aligned"
      record_size="$total_size"
      base_size=$((48 + data_size))
      extension_size=$((record_size - base_size))
    fi

    test "$record_size" -le "$remaining" \
      || fail_microcode "$file record at byte $offset overruns the file"
    if test "$extension_size" -gt 0; then
      test "$extension_size" -ge 20 \
        || fail_microcode "$file record at byte $offset has a truncated extended-signature header"
      test $(((extension_size - 20) % 12)) -eq 0 \
        || fail_microcode "$file record at byte $offset has a malformed extended-signature table"
      extension_offset=$((offset + base_size))
      dd if="$file" of="$HEADER_TMP" bs=4 skip=$((extension_offset / 4)) \
        count=5 status=none
      set -- $(od -An -v -tu4 "$HEADER_TMP")
      test "$#" -eq 5 \
        || fail_microcode "$file record at byte $offset has an unreadable extended-signature header"
      signature_count="$1"
      test "$signature_count" -eq $(((extension_size - 20) / 12)) \
        || fail_microcode "$file record at byte $offset has an inconsistent extended-signature count"
      test "$3" -eq 0 -a "$4" -eq 0 -a "$5" -eq 0 \
        || fail_microcode "$file record at byte $offset has nonzero extended-signature reserved fields"
      # Match Linux's per-entry validation as well as the table checksum. Each
      # alternate signature replaces the main header's signature, platform
      # flags and checksum, so those three dwords must retain the same sum.
      main_signature_sum=$(((processor_signature + processor_flags + main_checksum) % 4294967296))
      signature_index=0
      while test "$signature_index" -lt "$signature_count"; do
        signature_offset=$((extension_offset + 20 + signature_index * 12))
        dd if="$file" of="$HEADER_TMP" bs=4 skip=$((signature_offset / 4)) \
          count=3 status=none
        set -- $(od -An -v -tu4 "$HEADER_TMP")
        test "$#" -eq 3 \
          || fail_microcode "$file record at byte $offset has an unreadable extended signature"
        extended_signature_sum=$((($1 + $2 + $3) % 4294967296))
        test "$extended_signature_sum" -eq "$main_signature_sum" \
          || fail_microcode "$file record at byte $offset has a bad extended-signature checksum"
        signature_index=$((signature_index + 1))
      done
      validate_checksum_region "$file" "$offset" "$base_size" \
        || fail_microcode "$file record at byte $offset has a bad update checksum"
      validate_checksum_region "$file" "$extension_offset" "$extension_size" \
        || fail_microcode "$file record at byte $offset has a bad extended-signature checksum"
    else
      validate_checksum_region "$file" "$offset" "$record_size" \
        || fail_microcode "$file record at byte $offset has a bad 32-bit checksum"
    fi

    offset=$((offset + record_size))
    records=$((records + 1))
  done

  test "$offset" -eq "$file_size" \
    || fail_microcode "$file did not end on a record boundary"
  printf 'validated %s (%s records)\n' "$file" "$records"
}

test "$#" -gt 0 || {
  echo "usage: validate-intel-ucode.sh FILE..." >&2
  exit 2
}
for file; do
  validate_microcode_file "$file"
done
