#!/usr/bin/env python3
"""Sort linux-firmware's WHENCE-listed blobs into per-family trees.

Usage: sort-firmware.py --families families.toml --source <tree> --out <dir> [--check]

Reads WHENCE from the source tree, assigns every File/RawFile/Link to a
family (or the ignore list) per families.toml, and refuses to continue if
anything is unclaimed or a family's blobs cite a licence text the family
does not declare. Then runs upstream's copy-firmware.sh --zstd into a
staging tree and moves each family's files into
<out>/family/<name>/usr/lib/firmware/, with the family's licence texts under
usr/share/licenses/firmware-<name>/. --check stops after the assignment.
"""
import argparse, fnmatch, os, re, shutil, subprocess, sys, tomllib
from collections import defaultdict


def fail(msg):
    print(f"sort-firmware: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_whence(path):
    """WHENCE is a sequence of blocks starting at 'Driver:' lines. Each block
    lists File:/RawFile: entries, Link: entries and free-text licence lines."""
    entries, cur = [], None

    def close_group():
        # A Licence: line covers the File/Link entries listed since the
        # previous one, so a block that lists two vendors' blobs (btusb:
        # Intel then Realtek) attributes each licence to its own files.
        if cur and cur["group"]:
            for f in cur["group"]:
                cur["file_licenses"][f] |= cur["group_licenses"]
            cur["group"], cur["group_licenses"] = [], set()

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("Driver:"):
                close_group()
                cur = {"driver": line[7:].strip(), "files": [], "links": [],
                       "file_licenses": defaultdict(set), "group": [], "group_licenses": set()}
                entries.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r'^(?:File|RawFile):\s*"?([^"]+?)"?\s*$', line)
            if m:
                if cur["group_licenses"]:
                    close_group()
                cur["files"].append(m.group(1))
                cur["group"].append(m.group(1))
                continue
            m = re.match(r"^Link:\s*(.+?)\s*->\s*(\S+)\s*$", line)
            if m:
                if cur["group_licenses"]:
                    close_group()
                # WHENCE escapes spaces in link names as "\ " (the Raspberry
                # Pi brcmfmac board files); copy-firmware.sh unescapes them.
                link = m.group(1).replace("\\ ", " ")
                cur["links"].append((link, m.group(2)))
                cur["group"].append(link)
                continue
            for tok in re.findall(r"LICEN[CS]E\.[\w.-]+", line):
                cur["group_licenses"].add(tok.rstrip("."))
    close_group()
    return entries


def driver_name(driver):
    return driver.split(" - ", 1)[0].strip()


def load_families(path):
    with open(path, "rb") as fh:
        doc = tomllib.load(fh)
    fams = {}
    for name, f in doc.get("family", {}).items():
        fams[name] = {
            "drivers": [re.compile(p) for p in f.get("drivers", [])],
            "paths": f.get("paths", []),
            "licenses": set(f.get("licenses", [])),
            "cfg": f,
        }
    ignore = doc.get("ignore", {})
    fams["<ignore>"] = {
        "drivers": [re.compile(p) for p in ignore.get("drivers", [])],
        "paths": ignore.get("paths", []),
        "licenses": set(),
        "cfg": {},
    }
    return fams


def assign(entries, fams):
    """Return {family: {"files": set, "links": [(l,t)], "licenses": set}} plus
    a list of unclaimed (driver, file) pairs."""
    out = defaultdict(lambda: {"files": set(), "links": [], "licenses": set()})
    file_owner, unclaimed = {}, []
    for e in entries:
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
            out[owner]["licenses"] |= e["file_licenses"][f]
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
            out[owner]["licenses"] |= e["file_licenses"][link]
            file_owner[link] = owner
    return out, unclaimed, file_owner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    fams = load_families(args.families)
    entries = parse_whence(os.path.join(args.source, "WHENCE"))
    assigned, unclaimed, file_owner = assign(entries, fams)

    problems = []
    for drv, f in unclaimed:
        problems.append(f"unclaimed: {f}  (Driver: {drv})")
    for fam, got in assigned.items():
        if fam == "<ignore>":
            continue
        declared = fams[fam]["licenses"]
        for lic in sorted(got["licenses"] - declared):
            problems.append(f"family {fam}: blobs cite {lic}, which the family does not declare")
        for lic in sorted(declared - got["licenses"]):
            problems.append(f"family {fam}: declares {lic}, which none of its blobs cite")
        for lic in sorted(declared):
            if not os.path.exists(os.path.join(args.source, "LICENSES", lic)):
                problems.append(f"family {fam}: licence text {lic} does not exist upstream")
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
        licdir = os.path.join(root, "usr", "share", "licenses",
                              f"org.kernel.linux-firmware-{fam}")
        os.makedirs(licdir, exist_ok=True)
        for lic in sorted(fams[fam]["licenses"]):
            shutil.copy2(os.path.join(args.source, "LICENSES", lic), os.path.join(licdir, lic))

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
