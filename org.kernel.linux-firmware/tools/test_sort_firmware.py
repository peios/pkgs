#!/usr/bin/env python3
"""Unit tests for sort-firmware.py's WHENCE licence accounting (PEI-1166).

Run: python3 tools/test_sort_firmware.py
"""
import importlib.util, os, tempfile, textwrap, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sort_firmware", os.path.join(HERE, "sort-firmware.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)

RULE = "-" * 74

WHENCE = textwrap.dedent(f"""\
    Some preamble text.

    {RULE}

    Driver: vend - A vendor driver

    File: vend/a.bin
    Link: vend/a-link.bin -> a.bin

    Licence: Redistributable. See LICENCE.vend for details.

    {RULE}

    Driver: cxa - first of two drivers sharing one licence

    File: cxa.fw

    Driver: cxb - second driver

    File: cxb.fw

    Licence: Redistributable. See LICENSE.cx and NOTICE.cx for details.

    {RULE}

    Driver: split - two vendors in one block

    File: one/x.bin

    Licence: Redistributable. See LICENCE.vend for details.

    File: two/y.bin

    Licence: GPLv2 or later. See GPL-2.0 for details.

    {RULE}

    Driver: old - found in hex form

    File: old/fw.bin

    Licence: Allegedly GPLv2+, but no source visible. Marked:
        Copyright Someone

    {RULE}

    Driver: dual - pcmcia

    File: cis/d.cis

    Licence: Dual GPLv2/MPL
    """)

FAMILIES = textwrap.dedent("""\
    [family.a]
    description = "a"
    drivers = ["vend", "cxa", "cxb", "old", "dual", "split"]
    license = "GPL-2.0-only AND GPL-2.0-or-later AND LicenseRef-CX AND LicenseRef-Vend"

    [family.b]
    description = "b"
    paths = ["two/*"]
    license = "GPL-2.0-or-later"

    [licence_ids]
    "LICENCE.vend" = "LicenseRef-Vend"
    "LICENSE.cx"   = "LicenseRef-CX"
    """)

TEXTS = ["LICENCE.vend", "LICENSE.cx", "NOTICE.cx", "GPL-2.0"]


class SortFirmwareLicences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        os.makedirs(os.path.join(self.src, "LICENSES"))
        for t in TEXTS:
            open(os.path.join(self.src, "LICENSES", t), "w").write(t + "\n")
        self.write(WHENCE, FAMILIES)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, whence, families):
        open(os.path.join(self.src, "WHENCE"), "w").write(whence)
        self.fam_path = os.path.join(self.src, "families.toml")
        open(self.fam_path, "w").write(families)

    def run_account(self):
        fams, ids = sf.load_families(self.fam_path)
        entries, sections, problems = sf.parse_whence(os.path.join(self.src, "WHENCE"))
        assigned, derived, problems = sf.account(fams, ids, entries, problems, self.src)
        return assigned, derived, problems, sections

    def test_derives_texts_and_spdx_per_family(self):
        assigned, derived, problems, _ = self.run_account()
        self.assertEqual(problems, [])
        texts_a, terms_a = derived["a"]
        self.assertEqual(texts_a, {"LICENCE.vend", "LICENSE.cx", "NOTICE.cx", "GPL-2.0"})
        self.assertEqual(terms_a, {"LicenseRef-Vend", "LicenseRef-CX", "GPL-2.0-or-later", "GPL-2.0-only"})
        # The split block: family b took two/y.bin by path, and only y.bin's
        # licence; x.bin's vendor licence stays with the driver match (a).
        self.assertEqual(derived["b"], ({"GPL-2.0"}, {"GPL-2.0-or-later"}))
        self.assertIn("one/x.bin", assigned["a"]["files"])

    def test_licence_spans_drivers_in_a_section(self):
        entries, _, problems = sf.parse_whence(os.path.join(self.src, "WHENCE"))
        self.assertEqual(problems, [])
        cxa = next(e for e in entries if e["driver"].startswith("cxa"))
        self.assertIn(("text", "LICENSE.cx"), cxa["file_items"]["cxa.fw"])

    def test_excerpt_keeps_upstream_wording(self):
        assigned, _, _, sections = self.run_account()
        text = sf.excerpt(sections, assigned["a"]["sections"])
        self.assertIn("Allegedly GPLv2+, but no source visible", text)
        self.assertIn("Copyright Someone", text)
        self.assertIn("Dual GPLv2/MPL", text)
        self.assertNotIn("Some preamble", text)

    def test_unrecognised_declaration_fails(self):
        self.write(WHENCE.replace("Dual GPLv2/MPL", "Public domain, probably"), FAMILIES)
        *_, problems, _ = self.run_account()
        self.assertTrue(any("unrecognised licence declaration" in p for p in problems), problems)

    def test_unmapped_vendor_text_fails(self):
        self.write(WHENCE, FAMILIES.replace('"LICENSE.cx"   = "LicenseRef-CX"\n', ""))
        *_, problems, _ = self.run_account()
        self.assertTrue(any("does not map" in p for p in problems), problems)

    def test_declared_spdx_must_match(self):
        self.write(WHENCE, FAMILIES.replace("GPL-2.0-only AND ", ""))
        *_, problems, _ = self.run_account()
        self.assertTrue(any("family a: license must be" in p for p in problems), problems)

    def test_unlicensed_file_fails(self):
        self.write(WHENCE + f"\n{RULE}\n\nDriver: vend - more\n\nFile: vend/b.bin\n", FAMILIES)
        *_, problems, _ = self.run_account()
        self.assertIn("family a: vend/b.bin has no licence in WHENCE", problems)

    def test_staged_texts_checked(self):
        _, derived, _, _ = self.run_account()
        staged = os.path.join(self.src, "family")
        for fam, (texts, _) in derived.items():
            d = os.path.join(staged, fam, sf.LICENCE_DIR.format(fam))
            os.makedirs(d)
            for t in texts | {sf.EXCERPT}:
                open(os.path.join(d, t), "w").close()
        self.assertEqual(sf.check_staged(staged, derived), [])
        os.unlink(os.path.join(staged, "a", sf.LICENCE_DIR.format("a"), "GPL-2.0"))
        self.assertEqual(sf.check_staged(staged, derived), ["family a: staged licences lack GPL-2.0"])


if __name__ == "__main__":
    unittest.main()
