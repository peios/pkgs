#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Convert Mozilla certdata.txt into Peios's ServerAuth PEM bundle.

Only certificates whose matching trust object marks CKA_TRUST_SERVER_AUTH as
CKT_NSS_TRUSTED_DELEGATOR are emitted. Parsing and identity checks fail closed:
malformed objects, duplicate identities or certificate bytes, orphan trust
records, and unknown ServerAuth trust values cannot silently alter the store.
"""

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import sys

CERTIFICATE = "CKO_CERTIFICATE"
TRUST = "CKO_NSS_TRUST"
ROOT_LIST = "CKO_NSS_BUILTIN_ROOT_LIST"
TRUSTED_DELEGATOR = "CKT_NSS_TRUSTED_DELEGATOR"
NOT_TRUSTED = "CKT_NSS_NOT_TRUSTED"
MUST_VERIFY = "CKT_NSS_MUST_VERIFY_TRUST"
SERVER_AUTH_VALUES = {TRUSTED_DELEGATOR, NOT_TRUSTED, MUST_VERIFY}
ATTRIBUTE = re.compile(r"^CKA_[A-Z0-9_]+$")
OCTAL_BLOCK = re.compile(rb"(?:\\[0-3][0-7][0-7])*")
EXPECTED_KINDS = {
    "CKA_CLASS": {"CK_OBJECT_CLASS"},
    "CKA_LABEL": {"UTF8"},
    "CKA_ISSUER": {"MULTILINE_OCTAL"},
    "CKA_SERIAL_NUMBER": {"MULTILINE_OCTAL"},
    "CKA_VALUE": {"MULTILINE_OCTAL"},
    "CKA_TRUST_SERVER_AUTH": {"CK_TRUST"},
    "CKA_NSS_SERVER_DISTRUST_AFTER": {"CK_BBOOL", "MULTILINE_OCTAL"},
}


class ConversionError(ValueError):
    """certdata cannot be converted without guessing."""


def parse_octal(lines, attribute, start_line):
    encoded = "".join(line.strip() for line in lines).encode("ascii", "strict")
    if not encoded or OCTAL_BLOCK.fullmatch(encoded) is None:
        raise ConversionError(
            f"line {start_line}: {attribute} has an empty or malformed MULTILINE_OCTAL value"
        )
    return bytes(int(encoded[i + 1:i + 4], 8) for i in range(0, len(encoded), 4))


def parse_utf8(value, line_number):
    try:
        decoded = ast.literal_eval(value)
    except (SyntaxError, ValueError) as error:
        raise ConversionError(f"line {line_number}: malformed UTF8 value") from error
    if not isinstance(decoded, str) or "\n" in decoded or "\r" in decoded:
        raise ConversionError(f"line {line_number}: UTF8 value must be one quoted line")
    return decoded


def parse_objects(text):
    """Parse certdata objects while rejecting malformed or ambiguous input."""
    objects = []
    current = {}
    pending = None
    octal_lines = []
    saw_begin = False

    for line_number, line in enumerate(text.splitlines(), 1):
        if pending is not None:
            if line.strip() == "END":
                name, start_line = pending
                current[name] = parse_octal(octal_lines, name, start_line)
                pending = None
                octal_lines = []
            else:
                octal_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "BEGINDATA":
            if saw_begin or current or objects:
                raise ConversionError(f"line {line_number}: duplicate or misplaced BEGINDATA")
            saw_begin = True
            continue
        if not saw_begin:
            raise ConversionError(f"line {line_number}: data appears before BEGINDATA")
        if stripped == "END":
            raise ConversionError(f"line {line_number}: unexpected END")

        parts = stripped.split(None, 2)
        if len(parts) < 2 or ATTRIBUTE.fullmatch(parts[0]) is None:
            raise ConversionError(f"line {line_number}: malformed attribute line")
        name, kind = parts[:2]
        value = parts[2] if len(parts) == 3 else ""
        if name in EXPECTED_KINDS and kind not in EXPECTED_KINDS[name]:
            raise ConversionError(
                f"line {line_number}: {name} has unexpected value kind {kind}"
            )
        if name == "CKA_CLASS" and current:
            objects.append(current)
            current = {}
        if name in current:
            raise ConversionError(f"line {line_number}: duplicate attribute {name}")
        if kind == "MULTILINE_OCTAL":
            if value:
                raise ConversionError(f"line {line_number}: trailing data after MULTILINE_OCTAL")
            pending = (name, line_number)
        elif kind == "UTF8":
            if not value:
                raise ConversionError(f"line {line_number}: malformed attribute line")
            current[name] = parse_utf8(value, line_number)
        else:
            if not value:
                raise ConversionError(f"line {line_number}: malformed attribute line")
            current[name] = value

    if not saw_begin:
        raise ConversionError("missing BEGINDATA")
    if pending is not None:
        raise ConversionError(f"line {pending[1]}: unterminated {pending[0]} MULTILINE_OCTAL")
    if current:
        objects.append(current)
    return objects


def label_of(obj):
    label = obj.get("CKA_LABEL", "(unnamed)")
    if not isinstance(label, str) or "\n" in label or "\r" in label:
        raise ConversionError("certificate label is not one safe line")
    return label


def object_key(obj, kind):
    issuer = obj.get("CKA_ISSUER")
    serial = obj.get("CKA_SERIAL_NUMBER")
    if not isinstance(issuer, bytes) or not issuer or not isinstance(serial, bytes) or not serial:
        raise ConversionError(f"{kind} {label_of(obj)!r} has no non-empty issuer/serial identity")
    return issuer, serial


def convert(text):
    """Return sorted (label, fingerprint, DER) entries and conversion counts."""
    certificates = {}
    trust = {}
    root_lists = 0
    for obj in parse_objects(text):
        klass = obj.get("CKA_CLASS")
        if klass == ROOT_LIST:
            root_lists += 1
            continue
        if klass == CERTIFICATE:
            key = object_key(obj, "certificate")
            der = obj.get("CKA_VALUE")
            if not isinstance(der, bytes) or not der:
                raise ConversionError(f"certificate {label_of(obj)!r} has no DER value")
            if key in certificates:
                raise ConversionError(f"duplicate certificate identity for {label_of(obj)!r}")
            certificates[key] = obj
            continue
        if klass == TRUST:
            key = object_key(obj, "trust object")
            if key in trust:
                raise ConversionError(f"duplicate trust identity for {label_of(obj)!r}")
            trust[key] = obj
            continue
        raise ConversionError(f"unsupported or missing CKA_CLASS {klass!r}")

    if root_lists != 1:
        raise ConversionError(f"expected exactly one builtin root-list marker, found {root_lists}")
    cert_keys, trust_keys = set(certificates), set(trust)
    if cert_keys != trust_keys:
        raise ConversionError(
            f"certificate/trust identity mismatch: {len(cert_keys - trust_keys)} certificate(s) "
            f"without trust and {len(trust_keys - cert_keys)} trust object(s) without certificate"
        )

    counts = {
        "certificates": len(certificates),
        "trust_objects": len(trust),
        "trusted": 0,
        "distrusted": 0,
        "other_purpose": 0,
        "untrusted": 0,
        "distrust_after": 0,
    }
    entries = []
    all_fingerprints = {}
    for key, cert in certificates.items():
        der = cert["CKA_VALUE"]
        fingerprint = hashlib.sha256(der).hexdigest()
        if fingerprint in all_fingerprints:
            raise ConversionError(
                f"duplicate certificate bytes for {label_of(cert)!r} and "
                f"{all_fingerprints[fingerprint]!r}"
            )
        all_fingerprints[fingerprint] = label_of(cert)

        record = trust[key]
        server_auth = record.get("CKA_TRUST_SERVER_AUTH")
        if server_auth not in SERVER_AUTH_VALUES:
            raise ConversionError(
                f"trust object {label_of(record)!r} has unknown ServerAuth value {server_auth!r}"
            )
        if server_auth == NOT_TRUSTED:
            counts["distrusted"] += 1
        elif server_auth == MUST_VERIFY:
            counts["other_purpose"] += 1
        else:
            counts["trusted"] += 1
            if record.get("CKA_NSS_SERVER_DISTRUST_AFTER") not in (None, "CK_FALSE"):
                counts["distrust_after"] += 1
            entries.append((label_of(cert), fingerprint, der))

    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return entries, counts


def to_pem(der):
    body = base64.b64encode(der).decode("ascii")
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n"


def render(entries, source):
    out = [
        "# Mozilla's CA root store, as shipped by org.mozilla.ca-certificates.\n",
        "#\n",
        "# This file is package DATA, not configuration. trustd composes the\n",
        "# machine store from it and Machine\\System\\Trust\\Certificates.\n",
        "# Use `trust add` or `trust distrust` for local trust decisions.\n",
        "#\n",
        f"# Source: {source}\n",
        "# Included only when CKA_TRUST_SERVER_AUTH is\n",
        "# CKT_NSS_TRUSTED_DELEGATOR.\n",
        f"# Trusted roots: {len(entries)}.\n\n",
    ]
    for label, fingerprint, der in entries:
        out.append(f"# {label}\n# SHA-256 {fingerprint}\n")
        out.append(to_pem(der))
        out.append("\n")
    return "".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certdata", help="Mozilla certdata.txt")
    parser.add_argument("-o", "--output", required=True, help="PEM bundle to write")
    parser.add_argument("--floor", type=int, default=100, help="minimum accepted trusted-root count")
    parser.add_argument("--source", default="certdata.txt", help="provenance text for the header")
    parser.add_argument("--stats", help="write deterministic JSON conversion statistics")
    args = parser.parse_args()

    try:
        text = Path(args.certdata).read_text(encoding="utf-8", errors="strict")
        entries, counts = convert(text)
        if len(entries) < args.floor:
            raise ConversionError(f"{len(entries)} trusted roots is below the floor of {args.floor}")
        output = render(entries, args.source)
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8", newline="\n")
        output_path.chmod(0o644)
        if args.stats:
            Path(args.stats).write_text(
                json.dumps(counts, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="ascii",
                newline="\n",
            )
    except (ConversionError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        "certdata: {certificates} certificates and {trust_objects} trust objects; "
        "{trusted} trusted for ServerAuth, {distrusted} distrusted, "
        "{other_purpose} not delegated for ServerAuth; {distrust_after} trusted "
        "roots carry a cutoff a flat PEM bundle cannot enforce".format(**counts),
        file=sys.stderr,
    )
    print(f"wrote {args.output}: {len(entries)} roots", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
