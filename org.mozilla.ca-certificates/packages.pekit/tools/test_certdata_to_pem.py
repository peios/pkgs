#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Fail-closed fixtures for certdata-to-pem.py."""

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("certdata-to-pem.py")
SPEC = importlib.util.spec_from_file_location("certdata_to_pem", MODULE_PATH)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


def octal(data):
    return "".join(f"\\{byte:03o}" for byte in data)


def multiline(name, data):
    return f"{name} MULTILINE_OCTAL\n{octal(data)}\nEND\n"


def root_list():
    return (
        "BEGINDATA\n"
        "CKA_CLASS CK_OBJECT_CLASS CKO_NSS_BUILTIN_ROOT_LIST\n"
        'CKA_LABEL UTF8 "Mozilla Builtin Roots"\n'
    )


def certificate(label, issuer, serial, der):
    return (
        "CKA_CLASS CK_OBJECT_CLASS CKO_CERTIFICATE\n"
        f'CKA_LABEL UTF8 "{label}"\n'
        + multiline("CKA_ISSUER", issuer)
        + multiline("CKA_SERIAL_NUMBER", serial)
        + multiline("CKA_VALUE", der)
    )


def trust(label, issuer, serial, status=converter.TRUSTED_DELEGATOR, comment=False):
    middle = "# For Server Distrust After:\n" if comment else ""
    return (
        "CKA_CLASS CK_OBJECT_CLASS CKO_NSS_TRUST\n"
        f'CKA_LABEL UTF8 "{label}"\n'
        + multiline("CKA_ISSUER", issuer)
        + middle
        + multiline("CKA_SERIAL_NUMBER", serial)
        + f"CKA_TRUST_SERVER_AUTH CK_TRUST {status}\n"
        "CKA_NSS_SERVER_DISTRUST_AFTER CK_BBOOL CK_FALSE\n"
    )


class ConverterFixtures(unittest.TestCase):
    def complete(self, certs, trusts):
        return root_list() + "".join(certs) + "".join(trusts)

    def test_trust_selection_comment_handling_and_determinism(self):
        text = self.complete(
            [
                certificate("Zulu", b"issuer-z", b"1", b"der-z"),
                certificate("Alpha", b"issuer-a", b"2", b"der-a"),
            ],
            [
                trust("Zulu", b"issuer-z", b"1", comment=True),
                trust("Alpha", b"issuer-a", b"2", converter.MUST_VERIFY),
            ],
        )
        first, counts = converter.convert(text)
        second, second_counts = converter.convert(text)
        self.assertEqual(first, second)
        self.assertEqual(counts, second_counts)
        self.assertEqual([entry[0] for entry in first], ["Zulu"])
        self.assertEqual(counts["trusted"], 1)
        self.assertEqual(counts["other_purpose"], 1)

    def test_unicode_label_is_preserved_as_utf8_comment(self):
        text = self.complete(
            [certificate("Ő Root", b"issuer", b"1", b"der")],
            [trust("Ő Root", b"issuer", b"1")],
        )
        entries, _ = converter.convert(text)
        rendered = converter.render(entries, "fixture")
        self.assertIn("# Ő Root\n", rendered)
        self.assertEqual(rendered.encode("utf-8").decode("utf-8"), rendered)

    def test_explicit_distrust_is_excluded(self):
        text = self.complete(
            [certificate("Distrusted", b"issuer", b"1", b"der")],
            [trust("Distrusted", b"issuer", b"1", converter.NOT_TRUSTED)],
        )
        entries, counts = converter.convert(text)
        self.assertEqual(entries, [])
        self.assertEqual(counts["distrusted"], 1)

    def assert_conversion_error(self, text, message):
        with self.assertRaisesRegex(converter.ConversionError, message):
            converter.convert(text)

    def test_duplicate_certificate_identity_is_rejected(self):
        cert = certificate("One", b"issuer", b"1", b"der")
        self.assert_conversion_error(
            self.complete([cert, cert], [trust("One", b"issuer", b"1")]),
            "duplicate certificate identity",
        )

    def test_duplicate_trust_identity_is_rejected(self):
        trust_record = trust("One", b"issuer", b"1")
        self.assert_conversion_error(
            self.complete(
                [certificate("One", b"issuer", b"1", b"der")],
                [trust_record, trust_record],
            ),
            "duplicate trust identity",
        )

    def test_duplicate_certificate_fingerprint_is_rejected(self):
        self.assert_conversion_error(
            self.complete(
                [
                    certificate("One", b"issuer-1", b"1", b"same-der"),
                    certificate("Two", b"issuer-2", b"2", b"same-der"),
                ],
                [trust("One", b"issuer-1", b"1"), trust("Two", b"issuer-2", b"2")],
            ),
            "duplicate certificate bytes",
        )

    def test_orphan_certificate_or_trust_is_rejected(self):
        self.assert_conversion_error(
            self.complete([certificate("One", b"issuer", b"1", b"der")], []),
            "identity mismatch",
        )
        self.assert_conversion_error(
            self.complete([], [trust("One", b"issuer", b"1")]),
            "identity mismatch",
        )

    def test_unknown_or_missing_server_auth_is_rejected(self):
        unknown = trust("One", b"issuer", b"1", "CKT_VENDOR_SURPRISE")
        self.assert_conversion_error(
            self.complete(
                [certificate("One", b"issuer", b"1", b"der")],
                [unknown],
            ),
            "unknown ServerAuth value",
        )
        missing = trust("One", b"issuer", b"1").replace(
            f"CKA_TRUST_SERVER_AUTH CK_TRUST {converter.TRUSTED_DELEGATOR}\n", ""
        )
        self.assert_conversion_error(
            self.complete(
                [certificate("One", b"issuer", b"1", b"der")],
                [missing],
            ),
            "unknown ServerAuth value",
        )

    def test_malformed_octal_and_unterminated_blocks_are_rejected(self):
        malformed = root_list() + (
            "CKA_CLASS CK_OBJECT_CLASS CKO_CERTIFICATE\n"
            'CKA_LABEL UTF8 "Bad"\n'
            "CKA_ISSUER MULTILINE_OCTAL\n\\999\nEND\n"
        )
        self.assert_conversion_error(malformed, "malformed MULTILINE_OCTAL")
        unterminated = root_list() + (
            "CKA_CLASS CK_OBJECT_CLASS CKO_CERTIFICATE\n"
            'CKA_LABEL UTF8 "Bad"\n'
            "CKA_ISSUER MULTILINE_OCTAL\n\\001\n"
        )
        self.assert_conversion_error(unterminated, "unterminated")

    def test_duplicate_attribute_and_header_injection_are_rejected(self):
        duplicate = root_list() + (
            "CKA_CLASS CK_OBJECT_CLASS CKO_CERTIFICATE\n"
            'CKA_LABEL UTF8 "One"\n'
            'CKA_LABEL UTF8 "Two"\n'
        )
        self.assert_conversion_error(duplicate, "duplicate attribute")
        injected = root_list() + (
            "CKA_CLASS CK_OBJECT_CLASS CKO_CERTIFICATE\n"
            'CKA_LABEL UTF8 "One\\n# SHA-256 deadbeef"\n'
        )
        self.assert_conversion_error(injected, "one quoted line")

    def test_security_relevant_attribute_kind_is_rejected(self):
        wrong_kind = self.complete(
            [certificate("One", b"issuer", b"1", b"der")],
            [trust("One", b"issuer", b"1")],
        ).replace("CKA_TRUST_SERVER_AUTH CK_TRUST", "CKA_TRUST_SERVER_AUTH CK_BBOOL")
        self.assert_conversion_error(wrong_kind, "unexpected value kind")


if __name__ == "__main__":
    unittest.main()
