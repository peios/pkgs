#!/usr/bin/env python3
"""Convert Mozilla's certdata.txt into the PEM bundle Peios ships.

This is where the trust decision is encoded, so it is deliberately narrow:
a certificate is emitted only when its own trust object says
CKA_TRUST_SERVER_AUTH is CKT_NSS_TRUSTED_DELEGATOR. Everything else —
distrusted roots, roots trusted only for e-mail or code signing, roots with
no trust object at all — is left out and counted.

Peios' store is ServerAuth by construction. The other purposes exist in the
registry's schema (`Add\\<name>` carries `Purposes`) for certificates an
administrator adds, not for anything imported here.

Three controls guard the import, because every failure mode here is silent:

  --floor N   refuse to write a bundle with fewer than N roots, so a parser
              regression or a truncated download cannot ship a nearly-empty
              trust store.
  --previous  diff against the previously shipped bundle and print what was
              added and removed. A root appearing without explanation is
              what a compromise of the upstream would look like, so a bump
              is reviewed rather than taken on faith.
  --cross-check
              compare the result against curl's independently produced
              bundle. curl runs its own extractor over the same certdata.txt,
              so a disagreement means one of the two got the trust bits
              wrong. This is not optional decoration: it is what caught the
              bug where a comment *inside* a trust record split the object
              and silently dropped a trusted root. The floor did not catch
              it (120 roots is well above any sane floor) and a first build
              has no previous bundle to diff against.
"""

import argparse
import base64
import hashlib
import re
import sys

# The PKCS#11 object classes and trust values we care about.
CERTIFICATE = "CKO_CERTIFICATE"
TRUST = "CKO_NSS_TRUST"
TRUSTED_DELEGATOR = "CKT_NSS_TRUSTED_DELEGATOR"
NOT_TRUSTED = "CKT_NSS_NOT_TRUSTED"

OCTAL = re.compile(rb"\\([0-3][0-7][0-7])")


def parse_octal(lines):
    """MULTILINE_OCTAL: backslash-escaped octal bytes until END."""
    joined = "".join(lines).encode("ascii", "replace")
    return bytes(int(m.group(1), 8) for m in OCTAL.finditer(joined))


def parse_objects(text):
    """Every object in certdata.txt, as a dict of attribute -> value.

    Scalar attributes are kept as their trailing token; MULTILINE_OCTAL
    attributes as bytes.

    An object starts at CKA_CLASS and runs until the next one. Comments and
    blank lines are skipped, never treated as separators: Mozilla writes a
    "# For Server Distrust After:" comment *inside* a trust record, above
    CKA_NSS_SERVER_DISTRUST_AFTER, and splitting on it tears the trust bits
    off the issuer and serial that identify what they apply to. Roots so
    marked then look untrusted and vanish from the bundle without a word.
    """
    objects = []
    current = {}
    pending = None
    octal_lines = []
    for line in text.splitlines():
        if pending is not None:
            if line.strip() == "END":
                current[pending] = parse_octal(octal_lines)
                pending, octal_lines = None, []
            else:
                octal_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(" ", 2)
        if len(parts) < 2:
            continue
        name, kind = parts[0], parts[1]
        if name == "CKA_CLASS" and current:
            objects.append(current)
            current = {}
        value = parts[2] if len(parts) > 2 else ""
        if kind == "MULTILINE_OCTAL":
            pending, octal_lines = name, []
        elif kind == "UTF8":
            current[name] = value.strip('"')
        else:
            current[name] = value
    if current:
        objects.append(current)
    return objects


def label_of(obj):
    return obj.get("CKA_LABEL", "(unnamed)")


def convert(text):
    """Return (pem_entries, counts). An entry is (label, fingerprint, der)."""
    objects = parse_objects(text)
    certificates = {}
    trust = {}
    for obj in objects:
        klass = obj.get("CKA_CLASS")
        # Certificates and their trust objects are matched on the pair that
        # identifies a certificate in PKCS#11 terms: issuer and serial.
        key = (obj.get("CKA_ISSUER"), obj.get("CKA_SERIAL_NUMBER"))
        if klass == CERTIFICATE and obj.get("CKA_VALUE"):
            certificates[key] = obj
        elif klass == TRUST:
            trust[key] = obj

    entries = []
    counts = {
        "certificates": len(certificates),
        "trusted": 0,
        "distrusted": 0,
        "other_purpose": 0,
        "untrusted": 0,
        # Roots Mozilla trusts only for certificates issued before a cutoff
        # (CKA_NSS_SERVER_DISTRUST_AFTER). A flat PEM bundle cannot express
        # that and neither can any other trust store, so they are included,
        # as everywhere else — but they are counted so the caveat is visible.
        "distrust_after": 0,
    }
    for key, cert in sorted(certificates.items(), key=lambda kv: label_of(kv[1])):
        record = trust.get(key)
        if record is None:
            counts["untrusted"] += 1
            continue
        server_auth = record.get("CKA_TRUST_SERVER_AUTH", "")
        if server_auth == NOT_TRUSTED:
            counts["distrusted"] += 1
            continue
        if server_auth != TRUSTED_DELEGATOR:
            counts["other_purpose"] += 1
            continue
        der = cert["CKA_VALUE"]
        counts["trusted"] += 1
        if record.get("CKA_NSS_SERVER_DISTRUST_AFTER") not in (None, "CK_FALSE"):
            counts["distrust_after"] += 1
        entries.append((label_of(cert), hashlib.sha256(der).hexdigest(), der))
    return entries, counts


def to_pem(der):
    body = base64.b64encode(der).decode("ascii")
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n"


def render(entries, source):
    out = [
        "# Mozilla's CA root store, as shipped by the Peios ca-certificates package.\n",
        "#\n",
        "# This file is package DATA, not configuration: it is the input to the\n",
        "# machine's trust store, which trustd composes from this plus the\n",
        "# additions and distrusts under Machine\\System\\Trust\\Certificates.\n",
        "# Editing it changes nothing on a running machine — trustd renders the\n",
        "# store to /etc/ssl from here. To change what this machine trusts, use\n",
        "# `trust add` and `trust distrust`.\n",
        "#\n",
        f"# Source: {source}\n",
        "# Only roots whose CKA_TRUST_SERVER_AUTH is CKT_NSS_TRUSTED_DELEGATOR\n",
        f"# are included: {len(entries)} of them.\n",
        "\n",
    ]
    for label, fingerprint, der in entries:
        out.append(f"# {label}\n# SHA-256 {fingerprint}\n")
        out.append(to_pem(der))
        out.append("\n")
    return "".join(out)


def previous_fingerprints(path):
    """The fingerprints in an existing bundle, for the bump diff."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    found = {}
    label = "(unnamed)"
    for chunk in re.finditer(rb"# ([^\n]*)\n# SHA-256 ([0-9a-f]{64})\n", data):
        found[chunk.group(2).decode()] = chunk.group(1).decode()
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("certdata", help="Mozilla's certdata.txt")
    parser.add_argument("-o", "--output", required=True, help="the PEM bundle to write")
    parser.add_argument("--floor", type=int, default=100, help="refuse to write fewer than this many roots")
    parser.add_argument("--previous", help="a previously shipped bundle to diff against")
    parser.add_argument("--source", default="certdata.txt", help="provenance line for the header")
    parser.add_argument("--cross-check", help="curl's cacert.pem, to compare the trust decision against")
    parser.add_argument(
        "--cross-check-tolerance",
        type=int,
        default=5,
        help="how many roots may differ before the disagreement is treated as a bug rather than as upstream skew",
    )
    args = parser.parse_args()

    with open(args.certdata, "r", encoding="utf-8", errors="replace") as handle:
        entries, counts = convert(handle.read())

    print(
        "certdata: {certificates} certificate(s); {trusted} trusted for server authentication, "
        "{distrusted} explicitly distrusted, {other_purpose} trusted for other purposes only, "
        "{untrusted} with no trust record; {distrust_after} of the trusted carry a "
        "server-distrust-after cutoff a PEM bundle cannot express".format(**counts),
        file=sys.stderr,
    )

    if len(entries) < args.floor:
        print(
            f"error: {len(entries)} root(s) is below the floor of {args.floor}. "
            "That is a parser regression or a truncated download, not a very small trust store; "
            "refusing to ship it.",
            file=sys.stderr,
        )
        return 1

    if args.previous:
        before = previous_fingerprints(args.previous)
        if before is None:
            print(f"note: no previous bundle at {args.previous}; nothing to diff", file=sys.stderr)
        else:
            now = {fingerprint: label for label, fingerprint, _ in entries}
            added = [(f, l) for f, l in now.items() if f not in before]
            removed = [(f, l) for f, l in before.items() if f not in now]
            if not added and not removed:
                print("bundle: unchanged from the previous version", file=sys.stderr)
            for fingerprint, label in sorted(added, key=lambda x: x[1]):
                print(f"  + {label}  [{fingerprint[:16]}]", file=sys.stderr)
            for fingerprint, label in sorted(removed, key=lambda x: x[1]):
                print(f"  - {label}  [{fingerprint[:16]}]", file=sys.stderr)
            print(
                f"bundle: {len(added)} added, {len(removed)} removed — review these before publishing",
                file=sys.stderr,
            )

    if args.cross_check:
        try:
            with open(args.cross_check, "r", encoding="utf-8", errors="replace") as handle:
                other = set(re.findall(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", handle.read(), re.S))
            other = {hashlib.sha256(base64.b64decode(re.sub(r"\s", "", block))).hexdigest() for block in other}
        except OSError as error:
            print(f"error: cannot read the cross-check bundle: {error}", file=sys.stderr)
            return 1
        ours = {fingerprint for _, fingerprint, _ in entries}
        labels = {fingerprint: label for label, fingerprint, _ in entries}
        extra, missing = ours - other, other - ours
        if not extra and not missing:
            print(f"cross-check: identical to {args.cross_check} ({len(ours)} roots)", file=sys.stderr)
        else:
            for fingerprint in sorted(extra):
                print(f"  cross-check: we trust and they do not: {labels.get(fingerprint, '?')} [{fingerprint[:16]}]", file=sys.stderr)
            for fingerprint in sorted(missing):
                print(f"  cross-check: they trust and we do not: [{fingerprint[:16]}]", file=sys.stderr)
            # A root or two apart is the two extractors having run at
            # different moments against a moving branch. Dozens apart is a
            # disagreement about what the trust bits mean.
            if len(extra) + len(missing) > args.cross_check_tolerance:
                print(
                    f"error: {len(extra) + len(missing)} roots differ, over the tolerance of "
                    f"{args.cross_check_tolerance} — that is a disagreement about the trust bits, not upstream skew",
                    file=sys.stderr,
                )
                return 1
            print(
                f"cross-check: {len(extra) + len(missing)} root(s) differ, within tolerance — "
                "review the lines above; a small difference is normal skew between extraction runs",
                file=sys.stderr,
            )

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(render(entries, args.source))
    print(f"wrote {args.output}: {len(entries)} root(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
