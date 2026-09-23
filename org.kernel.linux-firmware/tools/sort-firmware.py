#!/usr/bin/env python3
"""Sort linux-firmware's WHENCE-listed blobs into per-family trees.

Usage: sort-firmware.py --families families.toml --source <tree>
                        (--out <dir> | --check [--staged <dir>/family])

Reads WHENCE from the source tree and assigns every File/RawFile/Link to a
family (or the ignore list) per families.toml. For each family it then
derives, from the licences WHENCE cites for that family's own files:

  * the licence texts to ship: every LICEN[CS]E.* and NOTICE.* file cited,
    plus the LICENSES/<id> text behind every free-licence declaration
    ("GPLv2 or later. See GPL-2.0", "MIT", "Allegedly GPLv2+", ...);
  * the SPDX expression: the AND of one term per cited licence, vendor texts
    through families.toml's [licence_ids] table, free declarations through
    FREE_LICENCES below.

It refuses to continue if anything is unclaimed, if a licence declaration is
not recognised, if a cited vendor text has no [licence_ids] entry, or if a
family's declared `license` differs from the derived expression. Then it runs
upstream's copy-firmware.sh --zstd into a staging tree and moves each
family's files into <out>/family/<name>/usr/lib/firmware/, with the family's
licence texts and a WHENCE excerpt (upstream's own wording and copyright
notices for every entry the family ships) under
usr/share/licenses/org.kernel.linux-firmware-<name>/.

--check stops after the accounting. With --staged it also verifies that each
staged family's licence directory holds exactly the derived texts.
"""
import argparse, fnmatch, os, re, shutil, subprocess, sys, tomllib
from collections import defaultdict

LICENCE_DIR = "usr/share/licenses/org.kernel.linux-firmware-{}"
EXCERPT = "WHENCE"

# Licence declarations WHENCE makes in words rather than by citing a vendor
# text. Each maps to the SPDX term Peios declares and the upstream LICENSES/
# text it ships. The patterns are anchored and closed: a declaration that
# matches none of them (and cites no vendor text) stops the build.
#
# "Allegedly ..." entries are upstream's own hedge (the firmware was found in
# hex form with a licence marking but no source). They are declared as the
# licence upstream names, the GPL text is shipped, and upstream's wording is
# preserved verbatim in the shipped WHENCE excerpt; Peios claims no more
# certainty than that. A bare "GPL" (no version) is GPL-1.0-or-later: the
# GPL lets the recipient choose any version, so the shipped GPL-2.0 text is
# one the recipient may elect. The two dual-licence declarations name
# alternatives whose texts upstream does not carry (an unversioned MPL,
# OpenIB.org BSD); Peios distributes those files under the GPLv2 branch it
# can document, and the excerpt records the dual grant.
FREE_LICENCES = [
    (r"Allegedly GPLv2\+", "GPL-2.0-or-later", "GPL-2.0"),
    (r"Allegedly GPLv2\b", "GPL-2.0-only", "GPL-2.0"),
    (r"Allegedly GPL\b", "GPL-1.0-or-later", "GPL-2.0"),
    (r"GPLv2 or later\b", "GPL-2.0-or-later", "GPL-2.0"),
    (r"GPLv2 or OpenIB\.org BSD\b", "GPL-2.0-only", "GPL-2.0"),
    (r"Dual GPLv2/MPL\b", "GPL-2.0-only", "GPL-2.0"),
    (r"GPLv2\.", "GPL-2.0-only", "GPL-2.0"),
    (r"GPLv3\.", "GPL-3.0-only", "GPL-3.0-only"),
    (r"MIT\b", "MIT", "MIT"),
    (r"Apache-2\.0\b", "Apache-2.0", "Apache-2.0"),
]

TOKEN = re.compile(r"(?:LICEN[CS]E|NOTICE)\.[\w.-]*\w")
LICENCE_LINE = re.compile(r"^Licen[cs]e:\s*(.*)$")


def fail(msg):
    print(f"sort-firmware: {msg}", file=sys.stderr)
    sys.exit(1)


def classify(text):
    """Return (spdx, text id) for a worded licence declaration, or None."""
    for pattern, spdx, text_id in FREE_LICENCES:
        if re.match(pattern, text):
            return spdx, text_id
    return None


def parse_whence(path):
    """WHENCE is a sequence of sections separated by rules of dashes. A
    section holds one or more blocks starting at 'Driver:' lines; each block
    lists File:/RawFile: entries and Link: entries, and licence lines apply to
    the File/Link entries listed since the previous licence line in the same
    section, across Driver: lines (the Conexant section lists four drivers
    and one licence). So a block that lists two vendors' blobs (btusb: Intel
    then Realtek) gets each licence attributed to its own files.

    Per entry: driver, files, links, section (index into `sections`, the raw
    text kept for the shipped excerpt), and file_items: path ->
    {("text", name) | ("term", spdx)}. `problems` collects licence
    declarations nothing recognises."""
    entries, sections, problems = [], [[]], []
    cur = None
    group = []  # (entry, path) listed since the last licence in this section
    pending = {"items": set(), "tokens": False, "words": []}

    def reset():
        nonlocal pending
        pending = {"items": set(), "tokens": False, "words": []}

    def close_group():
        # A worded declaration counts only when the group cites no vendor
        # text: "Redistributable. See LICENCE.x" is the vendor text's.
        if pending["words"] and not pending["tokens"]:
            for text in pending["words"]:
                got = classify(text)
                if got is None:
                    where = cur["driver"] if cur else "?"
                    problems.append(f"Driver {where!r}: unrecognised licence declaration: {text!r}")
                    continue
                pending["items"] |= {("term", got[0]), ("text", got[1])}
        if group and pending["items"]:
            for entry, f in group:
                entry["file_items"][f] |= pending["items"]
            group.clear()
        reset()

    def new_group_if_licensed():
        if pending["items"] or pending["words"]:
            close_group()

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if re.fullmatch(r"-{20,}", line.strip()):
                close_group()
                group.clear()  # anything still unlicensed stays so, and is reported
                sections.append([])
                continue
            sections[-1].append(line)
            if line.startswith("Driver:"):
                cur = {"driver": line[7:].strip(), "files": [], "links": [],
                       "section": len(sections) - 1, "file_items": defaultdict(set)}
                entries.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r'^(?:File|RawFile):\s*"?([^"]+?)"?\s*$', line)
            if m:
                new_group_if_licensed()
                cur["files"].append(m.group(1))
                group.append((cur, m.group(1)))
                continue
            m = re.match(r"^Link:\s*(.+?)\s*->\s*(\S+)\s*$", line)
            if m:
                new_group_if_licensed()
                # WHENCE escapes spaces in link names as "\ " (the Raspberry
                # Pi brcmfmac board files); copy-firmware.sh unescapes them.
                link = m.group(1).replace("\\ ", " ")
                cur["links"].append((link, m.group(2)))
                group.append((cur, link))
                continue
            tokens = TOKEN.findall(line)
            for tok in tokens:
                pending["items"].add(("text", tok))
                pending["tokens"] = True
            m = LICENCE_LINE.match(line)
            if m and not tokens:
                pending["words"].append(m.group(1).strip())
    close_group()
    sections = ["\n".join(lines).strip("\n") for lines in sections]
    return entries, sections, problems


def driver_name(driver):
    return driver.split(" - ", 1)[0].strip()


def load_families(path):
    with open(path, "rb") as fh:
        doc = tomllib.load(fh)
    fams = {}
    for name, f in doc.get("family", {}).items():
        for retired in ("licenses", "extra_licenses"):
            if retired in f:
                fail(f"family {name}: `{retired}` is derived from WHENCE now; remove it")
        fams[name] = {
            "drivers": [re.compile(p) for p in f.get("drivers", [])],
            "paths": f.get("paths", []),
            "license": f.get("license", ""),
            "cfg": f,
        }
    ignore = doc.get("ignore", {})
    fams["<ignore>"] = {
        "drivers": [re.compile(p) for p in ignore.get("drivers", [])],
        "paths": ignore.get("paths", []),
        "license": "",
        "cfg": {},
    }
    return fams, doc.get("licence_ids", {})


def assign(entries, fams):
    """Return {family: {"files": set, "links": [(l,t)], "items": set,
    "sections": [index], "unlicensed": [path]}}, the unclaimed (driver, file)
    pairs, and the file -> family map."""
    out = defaultdict(lambda: {"files": set(), "links": [], "items": set(),
                               "sections": [], "unlicensed": []})
    file_owner, unclaimed = {}, []

    def take(fam, idx, path, items):
        got = out[fam]
        got["items"] |= items
        if not items:
            got["unlicensed"].append(path)
        sec = entries[idx]["section"]
        if not got["sections"] or got["sections"][-1] != sec:
            got["sections"].append(sec)

    for idx, e in enumerate(entries):
        name = driver_name(e["driver"])
        whole = None
        for fam, spec in fams.items():
            if any(r.fullmatch(name) for r in spec["drivers"]):
                whole = fam
                break
        # A path pattern outranks the whole-block driver match: a block that
        # lists blobs for two vendors (btusb: Intel + Realtek Bluetooth) is
        # split by path, and the driver match takes what is left.
        for f in e["files"]:
            owner = None
            for fam, spec in fams.items():
                if any(fnmatch.fnmatchcase(f, p) for p in spec["paths"]):
                    owner = fam
                    break
            owner = owner or whole
            if owner is None:
                unclaimed.append((e["driver"], f))
                continue
            out[owner]["files"].add(f)
            take(owner, idx, f, e["file_items"][f])
            file_owner[f] = owner
        for link, target in e["links"]:
            tpath = os.path.normpath(os.path.join(os.path.dirname(link), target))
            owner = file_owner.get(tpath)
            if owner is None:
                # A link to a link, or to a file listed in another block: the
                # link follows the family that owns the link's own path.
                for fam, spec in fams.items():
                    if any(fnmatch.fnmatchcase(link, p) for p in spec["paths"]):
                        owner = fam
                        break
                owner = owner or whole
            if owner is None:
                unclaimed.append((e["driver"], f"{link} -> {target}"))
                continue
            out[owner]["links"].append((link, target))
            # A link is the file it points at; it carries that licence.
            items = e["file_items"][link] or e["file_items"].get(tpath, set())
            if not items and file_owner.get(tpath) == owner:
                items = {("linked", tpath)}
            take(owner, idx, link, items)
            file_owner[link] = owner
    for got in out.values():
        got["items"] = {i for i in got["items"] if i[0] != "linked"}
    return out, unclaimed, file_owner


def spdx_terms(expr):
    return {t.strip() for t in expr.split(" AND ") if t.strip()}


def derive(got, licence_ids, problems, fam):
    """Texts and SPDX terms for one family's cited licences."""
    texts, terms = set(), set()
    for kind, value in got["items"]:
        if kind == "text":
            texts.add(value)
            if value.startswith("NOTICE."):
                continue
            if value.startswith(("LICENCE.", "LICENSE.")):
                if value not in licence_ids:
                    problems.append(f"family {fam}: blobs cite {value}, which [licence_ids] does not map "
                                    "to an SPDX identifier (read it, then add it)")
                    continue
                terms.add(licence_ids[value])
        elif kind == "term":
            terms.add(value)
    return texts, terms


def account(fams, licence_ids, entries, parse_problems, source):
    assigned, unclaimed, file_owner = assign(entries, fams)
    problems = list(parse_problems)
    for drv, f in unclaimed:
        problems.append(f"unclaimed: {f}  (Driver: {drv})")
    derived, used_ids = {}, set()
    for fam, got in assigned.items():
        if fam == "<ignore>":
            continue
        for path in got["unlicensed"]:
            problems.append(f"family {fam}: {path} has no licence in WHENCE")
        texts, terms = derive(got, licence_ids, problems, fam)
        used_ids |= {t for t in texts if t in licence_ids}
        derived[fam] = (texts, terms)
        for text in sorted(texts):
            if not os.path.exists(os.path.join(source, "LICENSES", text)):
                problems.append(f"family {fam}: licence text {text} does not exist upstream")
        declared = spdx_terms(fams[fam]["license"])
        if declared != terms:
            problems.append(f"family {fam}: license must be {' AND '.join(sorted(terms))!r} "
                            f"(declared {fams[fam]['license']!r})")
    for lic in sorted(set(licence_ids) - used_ids):
        problems.append(f"[licence_ids] maps {lic}, which no packaged family cites")
    # Links must not cross families: a relative symlink whose target lands in
    # another package is broken on any system without both installed.
    for fam, got in assigned.items():
        for link, target in got["links"]:
            tpath = os.path.normpath(os.path.join(os.path.dirname(link), target))
            if file_owner.get(tpath, fam) != fam:
                problems.append(f"family {fam}: link {link} -> {target} crosses into {file_owner[tpath]}")
    for fam in fams:
        if fam != "<ignore>" and fam not in assigned:
            problems.append(f"family {fam}: matches nothing in WHENCE")
    return assigned, derived, problems


def excerpt(sections, idxs):
    header = ("This is an excerpt of linux-firmware's WHENCE: every entry with a file\n"
              "in this package, verbatim, including upstream's licence statements and\n"
              "copyright notices. Blocks that list files for more than one package\n"
              "appear in each of them.\n")
    rule = "\n" + "-" * 74 + "\n\n"
    return header + rule + rule.join(sections[i] for i in idxs) + "\n"


def check_staged(staged, derived):
    problems = []
    for fam, (texts, _) in sorted(derived.items()):
        licdir = os.path.join(staged, fam, LICENCE_DIR.format(fam))
        have = set(os.listdir(licdir)) if os.path.isdir(licdir) else set()
        want = texts | {EXCERPT}
        for missing in sorted(want - have):
            problems.append(f"family {fam}: staged licences lack {missing}")
        for extra in sorted(have - want):
            problems.append(f"family {fam}: staged licences carry {extra}, which its files do not cite")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--staged", help="with --check: the build's family/ directory to verify")
    args = ap.parse_args()

    fams, licence_ids = load_families(args.families)
    entries, sections, parse_problems = parse_whence(os.path.join(args.source, "WHENCE"))
    assigned, derived, problems = account(fams, licence_ids, entries, parse_problems, args.source)
    if args.staged:
        problems += check_staged(args.staged, derived)
    if problems:
        print("sort-firmware: families.toml does not account for this release:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        sys.exit(1)

    for fam in sorted(assigned):
        got = assigned[fam]
        print(f"sort-firmware: {fam:16s} {len(got['files']):5d} files {len(got['links']):5d} links")
    if args.check:
        return
    if not args.out:
        fail("--out is required without --check")

    stage = os.path.join(args.out, "stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    subprocess.run(["sh", "copy-firmware.sh", "--zstd", os.path.abspath(stage)],
                   cwd=args.source, check=True)

    def staged(path):
        # copy-firmware compresses File: entries (not RawFile:) and appends
        # .zst to links whose target was compressed; whichever exists wins.
        for cand in (path + ".zst", path):
            full = os.path.join(stage, cand)
            if os.path.lexists(full):
                return cand
        fail(f"{path}: not produced by copy-firmware.sh")

    for fam, got in assigned.items():
        if fam == "<ignore>":
            for f in sorted(got["files"]):
                os.unlink(os.path.join(stage, staged(f)))
            for link, _ in got["links"]:
                os.unlink(os.path.join(stage, staged(link)))
            continue
        root = os.path.join(args.out, "family", fam)
        fwdir = os.path.join(root, "usr", "lib", "firmware")
        for f in sorted(got["files"]) + [l for l, _ in got["links"]]:
            rel = staged(f)
            dst = os.path.join(fwdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(os.path.join(stage, rel), dst)
        licdir = os.path.join(root, LICENCE_DIR.format(fam))
        os.makedirs(licdir, exist_ok=True)
        for text in sorted(derived[fam][0]):
            shutil.copy2(os.path.join(args.source, "LICENSES", text), os.path.join(licdir, text))
        with open(os.path.join(licdir, EXCERPT), "w", encoding="utf-8") as fh:
            fh.write(excerpt(sections, got["sections"]))

    # Everything copy-firmware produced must now have been claimed.
    leftover = []
    for dirpath, _, files in os.walk(stage):
        for f in files:
            leftover.append(os.path.relpath(os.path.join(dirpath, f), stage))
    if leftover:
        fail("copy-firmware.sh produced files WHENCE assignment missed:\n  " + "\n  ".join(sorted(leftover)[:20]))
    shutil.rmtree(stage)

    # Broken relative symlinks would mean a link and its target were split.
    for fam in assigned:
        if fam == "<ignore>":
            continue
        root = os.path.join(args.out, "family", fam)
        for dirpath, _, files in os.walk(root):
            for f in files:
                p = os.path.join(dirpath, f)
                if os.path.islink(p) and not os.path.exists(p):
                    fail(f"broken symlink after sorting: {os.path.relpath(p, root)}")


if __name__ == "__main__":
    main()
