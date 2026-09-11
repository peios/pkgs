#!/usr/bin/env python3
"""Validate Linux-format AMD microcode containers and their assembly.

The format checks mirror the bounds and type checks performed by Linux's AMD
microcode loader.  They deliberately make no assertions about particular CPU
families, filenames, patch revisions, or release contents.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


CONTAINER_MAGIC = b"DMA\0"
CONTAINER_HEADER_SIZE = 12
EQUIV_ENTRY_SIZE = 16
EQUIV_TABLE_TYPE = 0
PATCH_HEADER_SIZE = 64
PATCH_SECTION_HEADER_SIZE = 8
PATCH_SECTION_TYPE = 1


class ValidationError(Exception):
    """A malformed or incorrectly assembled microcode input."""


@dataclass(frozen=True)
class Inventory:
    containers: int
    patches: int


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def fail(path: Path, offset: int, message: str) -> ValidationError:
    return ValidationError(f"{path}: byte {offset}: {message}")


def parse_container_file(path: Path, data: bytes) -> Inventory:
    offset = 0
    containers = 0
    patches = 0

    if not data:
        raise ValidationError(f"{path}: file is empty")

    while offset < len(data):
        container_start = offset
        remaining = len(data) - offset
        if remaining < CONTAINER_HEADER_SIZE:
            raise fail(path, offset, "truncated container header")
        if data[offset : offset + 4] != CONTAINER_MAGIC:
            raise fail(path, offset, "invalid container magic")

        table_type = u32(data, offset + 4)
        table_size = u32(data, offset + 8)
        if table_type != EQUIV_TABLE_TYPE:
            raise fail(path, offset + 4, f"invalid equivalence-table type {table_type}")
        if table_size % EQUIV_ENTRY_SIZE:
            raise fail(
                path,
                offset + 8,
                f"equivalence-table size {table_size} is not entry-aligned",
            )
        if table_size > remaining - CONTAINER_HEADER_SIZE:
            raise fail(path, offset + 8, "truncated equivalence table")

        offset += CONTAINER_HEADER_SIZE + table_size
        container_patches = 0

        while offset < len(data) and data[offset : offset + 4] != CONTAINER_MAGIC:
            remaining = len(data) - offset
            if remaining < PATCH_SECTION_HEADER_SIZE:
                raise fail(path, offset, "truncated patch-section header")

            section_type = u32(data, offset)
            patch_size = u32(data, offset + 4)
            if section_type != PATCH_SECTION_TYPE:
                raise fail(path, offset, f"invalid patch-section type {section_type}")
            if patch_size < PATCH_HEADER_SIZE:
                raise fail(path, offset + 4, f"patch size {patch_size} is too small")
            if patch_size > remaining - PATCH_SECTION_HEADER_SIZE:
                raise fail(path, offset + 4, f"patch size {patch_size} overruns the file")

            patch_start = offset + PATCH_SECTION_HEADER_SIZE
            patch_id = u32(data, patch_start + 4)
            nb_device_id = u32(data, patch_start + 16)
            sb_device_id = u32(data, patch_start + 20)
            if patch_id == 0:
                raise fail(path, patch_start + 4, "patch revision is zero")
            if nb_device_id or sb_device_id:
                raise fail(path, patch_start + 16, "chipset-specific patch is unsupported")

            offset += PATCH_SECTION_HEADER_SIZE + patch_size
            container_patches += 1
            patches += 1

        if container_patches == 0:
            raise fail(path, container_start, "container has no microcode patches")
        containers += 1

    return Inventory(containers=containers, patches=patches)


def source_containers(source_dir: Path) -> list[Path]:
    try:
        entries = list(os.scandir(source_dir))
    except OSError as error:
        raise ValidationError(f"{source_dir}: cannot scan source directory: {error}") from error

    paths = [
        Path(entry.path)
        for entry in entries
        if entry.name.startswith("microcode_amd")
        and entry.name.endswith(".bin")
        and entry.is_file(follow_symlinks=False)
    ]
    paths.sort(key=lambda path: os.fsencode(path.name))
    if not paths:
        raise ValidationError(f"{source_dir}: no microcode_amd*.bin containers found")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--assembled", required=True, type=Path)
    args = parser.parse_args()

    try:
        inputs = source_containers(args.source_dir)
        input_data: list[bytes] = []
        input_containers = 0
        input_patches = 0
        for path in inputs:
            data = path.read_bytes()
            inventory = parse_container_file(path, data)
            input_data.append(data)
            input_containers += inventory.containers
            input_patches += inventory.patches

        assembled = args.assembled.read_bytes()
        expected = b"".join(input_data)
        if assembled != expected:
            raise ValidationError(
                f"{args.assembled}: not the byte-exact, C-ordered concatenation "
                f"of all {len(inputs)} source files"
            )

        output_inventory = parse_container_file(args.assembled, assembled)
        expected_inventory = Inventory(input_containers, input_patches)
        if output_inventory != expected_inventory:
            raise ValidationError(
                f"{args.assembled}: parsed inventory {output_inventory} does not match "
                f"source inventory {expected_inventory}"
            )
    except (OSError, ValidationError) as error:
        print(f"amd microcode validation failed: {error}", file=sys.stderr)
        return 1

    print(
        f"validated {len(inputs)} source files, {input_containers} containers, "
        f"and {input_patches} patches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
