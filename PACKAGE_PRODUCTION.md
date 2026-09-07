# Package production campaign

> Temporary task ledger while Acta is unavailable. Move durable work history
> back to the relevant Acta items when service is restored; do not create
> duplicate tasks in the meantime.

## Objective

Work through the 113 recipes in this repository, bringing each to production
standard, validating it on the Debian reference rung and the native Peios
rung, and publishing signed packages to the local `peios` peipkg repository.
The upstream/dependency pass is complete; the first-party pass is now active,
starting with Atrium. If a package needs a product or architecture decision,
record the question here and continue with the next independent package.

## First-party namespace and acceptance

Peios-owned recipe directories and package names use the
`dev.peios.<product>` namespace. Existing unqualified package names receive
intentional `provides`/`replaces` migration metadata where needed. This is a
package identity rule: application catalogue IDs, service names, executable
names, registry paths, and protocol identities are separate interfaces and are
not renamed implicitly.

First-party production review uses Peios's own contracts rather than looking
for a nominal Fedora or Debian equivalent. In addition to the common package
closure above, each package must have:

- a documented product role and ownership boundary that agrees with `learn/`;
- an immutable, clean source identity and an explicit release/version policy;
- hermetic declared build inputs rather than undeclared sibling-tree fallbacks;
- complete runtime closure, service and registry integration, and intentional
  configuration, state, and upgrade ownership;
- least-privilege process identities and security metadata consistent with the
  relevant Peios specifications;
- meaningful unit, integration, installed-payload, hardening, and
  reproducibility gates; and
- appropriate runtime, development, debug, source, documentation, and
  component splits without fragmenting one inseparable product arbitrarily.

## Production closure

A completed upstream package normally has all of the following:

- reverse-DNS recipe and package names, with intentional migration
  `provides`/`replaces` metadata where an older unqualified name exists;
- automatic upstream release discovery bounded by a documented soft minimum
  and, where appropriate, a reviewed major-version ceiling;
- authenticated upstream source provenance with a full signer fingerprint
  wherever upstream signatures exist, plus a current lock;
- workspace-inherited build environments and distribution hardening flags;
- runtime, common/development, debug-info, debug-source, static, and source
  splits as appropriate for the payload;
- upstream tests plus staged payload, linkage, hardening, and determinism
  checks proportionate to the package;
- a successful Debian reference build and native Peios build;
- final signed `.peipkg` artifacts passing both `verify.sh` and the canonical
  `archive.VerifyFormat` implementation; and
- a successful `peipkg-repo verify` after publication.

## Checkpoint

- Last completed recipe: `org.gnu.gcc` at pkgs merge commit `4849061`.
- Completed: **85 / 113** recipes (75.2%).
- Current upstream/dependency pass: **85 / 85** recipes (100%).
- Current first-party pass: **0 / 28 published**; Atrium is packaging-complete
  on the host rung but blocked from release by the source/toolchain items below.
- Repository after GCC and the glibc metadata correction: index version 181,
  756 active entries, 1,463 archive-index entries, no verification problems.
- Signing fingerprint:
  `63977c7be45624999b88bac5aa55ab5280656ee076617a285c87602a0d980602`.

The 85 completed recipes are the currently tracked reverse-DNS recipe
directories. The upstream pass is complete.

## Remaining current-pass recipes

`dev.peios.atrium` is the current first-party recipe. Its proposed package
family and host build gates pass; its immutable/native release gates remain
blocked as recorded below.

## Deferred first-party recipes

`authd`, `build-essentials`, `coldplug`, `disk-boot`, `eventd`,
`feat-dynamic-boot`, `fsbase`, `kernel`, `libpeios`, `live-boot`, `loregd`,
`mockinit`, `netd`, `peinit`, `peios-dwe`, `peios-experimental`,
`peios-install`, `peios-kernel-only`, `peiosutils`, `peipkg`, `pnpd`,
`prelude`, `resolvd`, `timed`, and `trustd`, plus the already-qualified
`dev.peios.oobe` and `dev.peios.peios-installer` recipes.

## Follow-ups and known blockers

- `fsbase` security-descriptor overrides made the unprivileged package root
  expose a missing CLI surface rather than a package defect. Peipkg commit
  `76b65f4` adds deterministic `--record-xattrs` JSONL output using the
  composer's existing `RecordXattr` path; learn commit `2c8e18b` documents it,
  and the GCC branch's package-root wrapper records the attributes into its
  disposable temporary work area. The complete Peipkg test suite and a
  current-fsbase bwrap root smoke test pass.
- Add dependency-closure validation to `peipkg-repo verify` or a companion
  release gate. The post-GCC audit at index 181 used Peipkg's actual resolver
  against every active x86_64 non-debugsource package: 500 of 542 install goals
  resolve and 42 remain deferred. The unresolved paths terminate at
  `libpeios.so.0` (26), the composed-image `linux-kernel-headers` assumption
  (9), the legacy Binutils edge inside first-party `build-essentials-c` (3),
  first-party `peipkg` (2), and the unregistered first-party `initramfs` root
  used by disk/live boot (2). The audit caught and this pass corrected glibc
  revision 6's stale exact sibling constraints in revision 7. Deferred
  first-party `peios-experimental` still constrains the undotted CA version as
  `>= 20260830` and must migrate to the qualified package.
- Package GNU Readline separately and then enable it in Bash and `bc`.
  This was previously Acta item PEI-613 (`7qq9qu2h`).
- Allow recipes to declare precise source-package license metadata; until
  then, generated source packages necessarily share family metadata.
- Package native GDB and DWZ to enable Debugedit's optional find-debuginfo
  payload and the remaining 14 upstream integration tests on Peios.
- Resolve the long-term coexistence boundary between `peiosutils` and the
  POSIX/GNU-compatible tools needed by native package builds.
- Keep migration dependencies compose-safe while qualified and legacy package
  names coexist.
- The native build-root wrapper currently resolves every top-level artifact in
  `_pkgsOut_`, including superseded migrations. Legacy libxml2, libxslt,
  libtraceevent, and libtracefs pool artifacts were moved, recoverably, under
  `_pkgsOut_/archive/reverse-dns-migrated/` after their qualified replacements
  were published. Long term, compose roots should consume the signed active
  repository index rather than a flat historical pool glob.
- During Atrium's native compose check, the same flat-pool defect was found to
  affect the wider reverse-DNS migration. 805 legacy artifacts whose names are
  now provided by active qualified packages were moved recoverably to
  `_pkgsOut_/archive/reverse-dns-migrated/` (22 GCC artifacts and 783 other
  legacy-provider artifacts). No signed repository entry was deleted or
  rewritten. The wrapper now exposes an external delegated local source tree
  to both reference roots without exposing undeclared sibling checkouts.

## First-party current: Atrium 0.0.24-2

Atrium is packaged as a product family rather than a monolith or three
artificially independent executables:

- `dev.peios.atrium`: the default-product package, depending on the complete
  production app set;
- `dev.peios.atrium-core`: `atriumd`, `atrium-server`, `atrium-session`, and
  the inert service registry seed, upgraded atomically because none has an
  independent supported lifecycle;
- five independently installable noarch application packages: About,
  Packages, Registry, Services, and Terminal;
- conventional `dev.peios.atrium-debuginfo` and
  `dev.peios.atrium-debugsource` packages; and
- a generated `dev.peios.atrium-source` package once a reproducible Git source
  exists.

Events, Networking, and Principals are explicit placeholder applications and
are excluded from the production payload. There is intentionally no `-devel`
package: the browser SDK is embedded in the runtime and Atrium installs no
public headers, link libraries, or standalone build interface. The old
monolithic `atriumd` package is migrated through the default product's
`provides`/`replaces` metadata. The Terminal package carries the matching
xterm.js/addon-fit MIT notice as well as Atrium's own licence.

The complete host-toolchain package gate passes: all five Rust tests, including
the peinit descriptor/pidfd test, and an installed-payload smoke spanning the
daemon/server/session boundary, authentication relay, cookie lifecycle,
catalogue and asset serving, traversal rejection, and logout. All three
binaries pass PIE, full RELRO, BIND_NOW, NX-stack, RELR, build-ID, no-rpath,
split-debug, debug-source, and checkout-path-leak checks. All nine binary/meta
artifacts pass `verify.sh`, and `peipkg-compose` accepts their canonical format,
resolves their complete current dependency closure, and materialises exactly
the five production apps and three Atrium executables.

Release publication is deliberately blocked rather than weakened:

- the active Peios Rust/Cargo package is 1.83.0, while Atrium uses edition 2024
  and therefore requires at least 1.85; the recipe now declares that floor;
- Atrium has no configured canonical Git remote or release tags, so the
  catalogue can currently provide only a local developer source and cannot
  emit a reproducible corresponding-source package;
- Atrium's lock graph contains path dependencies on sibling `peios-rs` and
  `authd` checkouts, which an immutable Atrium source snapshot would not
  contain; those inputs need a deliberate release-bundle, vendoring, or
  separately versioned Git-source design; and
- Git-tag signature enforcement is deferred by product decision, but immutable
  clean source identity is not.

## Latest completion: GCC 16.2.0-2

`org.gnu.gcc` replaces the unqualified recipe with a 24-package compiler,
C++, preprocessor, runtime-library, development, static, documentation,
debug-info, debug-source, and corresponding-source family. It follows
authenticated GCC 16 point releases from a soft 16 floor, stops before GCC 17
for ABI/bootstrap and patch review, locks both currently published 16.x
releases, and pins the two official release signers' full primary
fingerprints.

The Debian reference rung passed before native closure. Two clean native Peios
builds then completed the full three-stage bootstrap and GCC's stage-2 versus
stage-3 object comparison, configured upstream test suites, staged C/C++ and
runtime-library consumers, package split checks, and PIE, RELRO, BIND_NOW,
RELR, build-ID, IBT, and SHSTK gates. All 24 payloads and normalized manifests
matched between the native builds. The signed packages pass both the shell and
canonical format verifiers and were published at index 180.

GCC's file/directory prefix shape exposed a false failure in `verify.sh`:
Python's tar reader removes directory trailing slashes before the script's
ordering comparison. Peipkg commit `41eb83f` now reconstructs the wire name;
the regression test and complete Peipkg suite pass. Final repository
verification after the glibc correction reports index 181, 756 active entries,
1,463 archived entries, and no problems.

## Previous completion: MPC 1.4.1-2

`org.gnu.mpc` replaces the unqualified recipe with runtime, development,
static, debug-info, debug-source, and source packages. It tracks authenticated
MPC 1.x releases from a soft 1.4 floor and pins Andreas Enge's full primary
fingerprint. MPC 1.4.1 was signed after that key's declared expiry, so the
recipe explicitly permits key expiry while Pekit continues to enforce the
fingerprint, cryptographic signature, revocation, critical-notation, and
timestamp checks.

Both clean Debian builds and both clean Peios-native builds passed all 75
upstream tests, installed shared/static API consumers, package splits,
hardening, SONAME, and payload reproducibility checks. The native shared object
retains IBT and SHSTK. All six artifacts are signed, pass `verify.sh`, and were
published at repository index 179; full repository verification reports 732
active entries, 1,218 archived entries, and no problems.

## Previous completion: glibc 2.44-7

`org.gnu.glibc` replaces the unqualified recipe with a complete reverse-DNS
family: runtime, loader/program, development, static, documentation, locale
source, corresponding source, debug, converter, utility, and generated locale
splits. It tracks authenticated GNU release archives from a soft 2.44 floor
with a major-version review ceiling below 3, pins Andreas K. Huettel's full
release-signing fingerprint, and retains the Peios fixed-identity NSS policy.
The staged ABI gate exposes and compiles every current Peios KACS, KMES, and
registry syscall alias against the matching kernel UAPI.

The native suite produced 7,135 PASS, 251 UNSUPPORTED, and 17 expected XFAIL
results with zero unexpected outcomes; the Debian reference produced 7,185
PASS, 210 UNSUPPORTED, and 17 XFAIL with zero unexpected outcomes. Both rungs
passed clean rebuild reproducibility, dynamic and static staged ABI consumers,
NSS/public-key/static policy checks, complete locale generation, hardening,
split-debug, and source-package gates. The corresponding PKM ABI generators
and public kernel-ABI documentation were updated separately so all 22 aliases
remain exact and mechanically checked.

All 221 revision-7 signed archives reuse the independently validated native
payload and carry exact revision-7 sibling dependencies. They pass both the
shell and canonical format verifiers, and repository verification passes at
index 181. Revision 7 supersedes revision 6, whose sibling constraints still
named revision 5; the post-GCC resolver audit found that stale edge before the
campaign was closed. The earlier revision-5 publication remains immutable
archive history because it carried accurate but release-ineligible `+dirty`
recipe provenance. The workspace ignores repository and pool worktree
symlinks, and release evidence lives outside the recipe worktree.

## Previous completion: Mozilla CA certificates 2026.09.06-1

`org.mozilla.ca-certificates` preserves Peios's Firefox release-branch trust
policy without build-time network access. Pekit's generic tracked-path Git
source follows the fixed `refs/heads/release` ref, versions only changes to
`security/nss/lib/ckfw/builtins/certdata.txt`, and locks the immutable commit
`e9961dcf47b3984082b4d854cb3743b7dfe79b53`, Git blob
`f2f8edc685ad3e5c38b79ab1d96c8dde79793fd6`, and blob SHA-256
`81b7f2576333a2e360e673f912d7b0b7a765d836c731003e348a46cac5d37198`.
The moving branch has no cryptographic release signature, so HTTPS plus the
committed immutable commit/blob lock is accurately retained as the TOFU
boundary. Locked materialisation and corresponding-source generation passed
offline with lazy fetching disabled; the source tar is deterministic and
contains only the tracked file.

The strict converter passed 11 malformed, duplicate, distrust, Unicode,
orphan, and determinism fixtures. The locked input contains 172 certificates
and 172 matching trust objects: 121 roots are delegated for TLS ServerAuth and
51 are excluded. OpenSSL loaded all 121 emitted certificates with unique
fingerprints, and the old and new bundle fingerprint sets are exactly
identical. Debian and native Peios builds passed exact payload/ownership,
source provenance, deterministic double conversion, and clean rebuild
comparison. The signed runtime and source packages carry clean recipe
provenance at `c09a75c`, passed both `verify.sh` and canonical
`archive.VerifyFormat`, and the repository passed verification at index 175.

One trust-format caveat remains explicit: one currently trusted Mozilla root
carries a distrust-after cutoff that a flat PEM bundle cannot encode. This
package therefore preserves the existing certificate set, but a future
structured trust input or trustd policy gate is needed to enforce temporal
cutoffs. The package provides the legacy `ca-certificates` name and replaces
the final undotted flat-pool release through `20260830-1`. That legacy artifact
is not active or historical in the signed repository; it remains only in the
flat compose pool, so no archival claim is made.

Published SHA-256 values:

- `org.mozilla.ca-certificates`: `ab5750e998af45c3e8e9842cd205aa5a5063e6f0e6aa112938b8be7ead68b7fa`
- `org.mozilla.ca-certificates-source`: `c85120b7e4e4f59333332e86cb65b6a032c79752cee4b7a54cdab09c8d71a496`

## Previous completion: Dash 0.5.13.5-3

Dash now tracks the official kernel.org Git tags from a soft 0.5.13.5 floor,
with a review ceiling below 0.6, and locks commit
`037bbdfd330017c368caf6242f977974123239b5`. The release tag is lightweight,
so HTTPS plus the immutable commit lock is recorded as the current TOFU
boundary rather than claiming unavailable Git-tag signature verification.
Pekit's version model and public documentation were extended first so all
four numeric components remain significant and `0.5.13.10` orders after
`0.5.13.9`.

After qualified glibc was published, revision 3 replaced the temporary legacy
dependency with `org.gnu.glibc >= 2.44`; both Debian and native builds proved
that transition and the repository advanced to index 178. Debian and native
builds passed same-path byte-reproducibility, the shipped
`make check` recursion, a staged shell-semantics suite, exact payload and
debug/source splits, PIE/RELRO/BIND_NOW/RELR/CET/build-ID checks, and a clean
native dependency resolution against the published pool. It provides the
legacy `dash` name and the `sh` role while replacing legacy Dash packages
through revision 2. Pekit's known source-license synthesis limitation
means the generated source manifest cannot separately express the locked
tree's GPL-2.0-or-later `src/mksignames.c` build helper; the emitted
binary/debug packages retain the accurate BSD-3-Clause payload license.

All four revision-3 signed packages have clean recipe provenance at pkgs commit
`cb3d955` and passed both the strict shell verifier and canonical
`archive.VerifyFormat`. The initial revision-1 artifacts, which had an
unresolvable early qualified-glibc edge and dirty-worktree provenance, were
superseded in the repository and moved recoverably from the flat pool to
`_pkgsOut_/archive/superseded-dash-transition/`. The repository audit passed
at index version 174 with 503 active and 764 archived entries; revision 3
passed again at index 178 with 726 active and 1,212 archived entries.

Current revision-3 SHA-256 values:

- `org.git.kernel.dash`: `df35be14581eb149a58b899a6e45d739039298c87cd473eea05c6dee3a8dad0e`
- `org.git.kernel.dash-debuginfo`: `776a42f132817f7fdaaef55fd3d14f98f316064ef679af86400ac56f2caaccf1`
- `org.git.kernel.dash-debugsource`: `10d10785a115f9691cd49bf0d9fafd34a0e0cc92ba9fb54f32412b29a61ca733`
- `org.git.kernel.dash-source`: `bd6902e026865570b3ba125fc4ac6107abf4f566341a9de8e42171e43366c2d3`

## Previous completion: libtracefs 1.8.3-2

Libtracefs tracks kernel.org's signed stable 1.x tags from a soft 1.8.3 floor
and locks commit `6fad6a14ba0d4c4b437d9e4eed7098d4bb07b4fc`. The 1.8.3 annotated tag was
independently verified against Steven Rostedt's key from kernel.org's official
`pgpkeys.git` snapshot. Debian and native passed the upstream CUnit runner's
build/help path, 45 HTML and 217 manual-page inventory, shared/static staged
consumers, ABI and pkg-config checks, split debug/source validation, hardening,
and clean byte-for-byte rebuild comparisons.

All seven signed packages passed both the strict shell verifier and canonical
`archive.VerifyFormat`. The repository audit passed at index version 171 with
499 active and 752 archived entries.

Published SHA-256 values:

- `org.linux.tracefs`: `dd02b946b9297d8bb90d8c7a5625faf69189275978f66c1e6368e3084990f4ac`
- `org.linux.tracefs-debuginfo`: `d1c57ee1a62a5388a0b0e454ce3824031860e946623005e24c63470e6523c7a0`
- `org.linux.tracefs-debugsource`: `7df6c32df662502f8b48b95309b51ba4885824ce7bc5ff9fcb98c1edcdcccd0c`
- `org.linux.tracefs-devel`: `bbc0ff6a20d4e3a94b33a2700f8cddf19d84b951d4305be2e1491103f8363ffa`
- `org.linux.tracefs-doc`: `8e1112ec40eec1455f257426d943bdcf86fec842e1d68a66f406db0db07b34be`
- `org.linux.tracefs-static`: `9f14662cb480406787aaf2ca64c57baed85336607a98139a459a993784e5d6da`
- `org.linux.tracefs-source`: `b1c4660712313d0b83c3b506459de2aefb09d4f137de7bc2ee1794aeab29f086`

## Previous completion: libtraceevent 1.9.0-2

Libtraceevent tracks kernel.org's stable signed 1.x Git tags from a soft 1.9
floor and locks 1.9.0 commit
`13701b5532e0c3295bf5670361692b0d0044228d`. Pekit cannot yet verify Git-tag
signatures, so the recipe accurately records the lock as a TOFU boundary
rather than claiming authenticated source verification. Debian passed all 12
upstream CUnit tests (46 assertions); native passed the maintained staged
shared/static consumers and all 13 plugin-loader tests. Both rungs passed the
documentation, ABI, split-debug, hardening, and byte-reproducibility gates.

All eight signed packages passed canonical `archive.VerifyFormat`; the unsigned
pre-publication artifacts also passed the strict shell verifier. The repository
audit passed at index version 170 with 492 active and 745 archived entries.

Published SHA-256 values:

- `org.linux.traceevent`: `0b750eff3f0a00b992c223a4cd9bcd0050a23f09dbcdf715b23432cfcb4f786a`
- `org.linux.traceevent-debuginfo`: `fb3886da849268e929dcb0c577179b1625f2da899f795f62c1ca3e1d899c10ed`
- `org.linux.traceevent-debugsource`: `2aedd79c41b0a85fc0fd59133d5d840f562d873e4b0d98c406aa94d3ba905fa0`
- `org.linux.traceevent-devel`: `b3b108ec27bb42abd919311ecdc7cd0ff4250676ac7152cdc555b43bd91a90e6`
- `org.linux.traceevent-doc`: `d6be9cf8f2f08eee88eb64c6b466acd20c91a6257aae6e98317e761b181bcd29`
- `org.linux.traceevent-libs`: `dafb8668b0e42b305b22f114a01be99cfd9c8a6d13fa5eb3a0a15eb1ec01d9a8`
- `org.linux.traceevent-static`: `be7da4d079340de2a86698b6414002b519979fb82ccf7017ac3ddcdc551a882a`
- `org.linux.traceevent-source`: `1f7b68982f0ae63396aad70ad4c154093a8c1d4bdad2102305ffa2e6d1aa5f3b`

## Previous completion: libxslt 1.1.45-1

Libxslt tracks GNOME's stable 1.1 releases from a soft 1.1.45 floor with a
review ceiling below 1.2. GNOME supplies an archive checksum but no detached
signature, so HTTPS plus Pekit's immutable SHA-256 lock is the documented
authentication boundary. Debian and native passed the full upstream suite,
staged XSLT/EXSLT and shared/static consumers, exact payload and debug splits,
hardening, and clean-rebuild byte comparisons.

All eight signed packages passed canonical format verification. Published
SHA-256 values:

- `org.gnome.libxslt`: `1586c8c3176bbc6f0c90a32ec51605eec6f20ed77eafe557498b70be8edae716`
- `org.gnome.libxslt-debuginfo`: `90ecafbfec0db23c16731ad75d9f80d3d93dee31a64adb1a6f468c86192689f2`
- `org.gnome.libxslt-debugsource`: `f275c2a15e130d86ff19f9d41d1f35e41563755b9b88431af5b49ca778f6a638`
- `org.gnome.libxslt-devel`: `e0525231bbe13f4b3344648ca228daad33c7fc023d02da8e49b4ffa045a4ded9`
- `org.gnome.libxslt-doc`: `bf89b1906ccb0c064b9069b1d99aefb0ab991ce19ee9e53a72baefa6ef020b24`
- `org.gnome.libxslt-static`: `71eb3b42e2ed9533f0e3d7f7dc2f3903fd78a57e056636a4904af91056cf10d3`
- `org.gnome.libxslt-utils`: `4495b2128244621d04920b4f1818dadfc55f53bb17f397bfb5c51faa082d6e87`
- `org.gnome.libxslt-source`: `988385f234242064cb0b09f30fc358cc95a909d4d3d1db7efc15be50f78e29cc`

## Previous completion: libxml2 2.15.4-1

Libxml2 tracks GNOME's 2.15 release line from a soft 2.15.3 floor and freezes
the SONAME-16 ABI. Debian passed the full upstream suite and 2,229 fuzz inputs;
both Debian and native passed staged XML/catalog/shared/static consumers,
complete package splits, hardening, and clean-rebuild reproducibility.

All eight signed packages passed canonical format verification. Published
SHA-256 values:

- `org.gnome.libxml2`: `2f2d01be10730190b3e7d8f0d38dd8e01bb476c9921262c3553bdb563648183f`
- `org.gnome.libxml2-debuginfo`: `c80e526a2683529629a6040fb419c56ee7c93cd3d6cb607d5200c151c6fdbadb`
- `org.gnome.libxml2-debugsource`: `a8768c7eb3e0b2f4734a54fa5fad9ac8794e4dc6df3ba929f04f8488aa2b3fc3`
- `org.gnome.libxml2-devel`: `dbc06a0eadddd15f38c26d13fc50f09391b59f1cd002a22b311d91e8391b8797`
- `org.gnome.libxml2-doc`: `d546083d4eb259eae3f9b98c42fb1384add74d6bcbf510cce5b2e0b757e1deea`
- `org.gnome.libxml2-static`: `f2f3f18aa508ceeb36f5442198c587d7c6d59245aff6775126bb4d95d33793bb`
- `org.gnome.libxml2-utils`: `9cad162d84c25189b87d866ebaa6ff5d58454ab576608cc6d87ba1699958c660`
- `org.gnome.libxml2-source`: `e1d7b2c5209e93dab1478ab32ef38c816a8b846e970f2bf4ed7c3d8433a46891`

## Dependency migration: XMLTO 0.0.29-2

XMLTO's Peipkg build and runtime dependencies now use the qualified libxml2,
libxslt, DocBook XML, and DocBook XSL package names. Its redundant build-time
Peiosutils edge was removed because the native C build baseline deliberately
supplies GNU Coreutils; the runtime Peiosutils dependency remains. Debian and
native package-all, upstream and staged DocBook tests, reproducibility,
hardening, and debug gates passed. All four signed artifacts passed both
archive verifiers, and the repository audit passed at index version 172.

Published SHA-256 values:

- `io.pagure.xmlto`: `266b533b0ae26706ae3767fb69440897fa4240af5131a4e89ac902aa382e1a03`
- `io.pagure.xmlto-debuginfo`: `3a05f5819bd7158e1bbb3e9465f3a9c1b345219f0d94fa19d461d9584e2823a7`
- `io.pagure.xmlto-debugsource`: `15e51e3a93864f0e1b529aa15a57b068f27a85c7ee48a9fea5c9752bde7a3c47`
- `io.pagure.xmlto-source`: `de3484c8904f187838eb5481971632bad38e5fde317049d44e89c7013e7e0ef7`

## Dependency migration: AsciiDoc 10.2.1-2

AsciiDoc's Peipkg build and runtime dependencies now use the qualified
libxml2, libxslt, DocBook XML, and DocBook XSL package names. Debian and native
revalidation passed, and both signed artifacts passed canonical verification.
The shell verifier retains its already-tracked directory/file prefix-order
false positive on the runtime archive; the source archive passes it.

Published SHA-256 values:

- `io.github.asciidoc-py.asciidoc`: `1709dfa30b635b281922f191e5057fb856d719a7bbb14d2f8bc0e5361ad35ed3`
- `io.github.asciidoc-py.asciidoc-source`: `51361b0890c45137449298d1f3eef661f2723437e0d67502ff82909f5ed8ac39`

## Previous completion: DocBook XSL 1.79.2-4

DocBook XSL tracks the authoritative non-namespaced DocBook 4 stylesheet
archive from a soft 1.79.2 floor. Upstream publishes no detached signature or
checksum manifest for this release, so the immutable Pekit SHA-256 lock is the
available provenance anchor. The noarch payload passed Debian and native Peios
builds, offline DTD/catalog resolution, HTML/XHTML/FO/man transformations,
permission normalization, and deterministic inventory checks.

The signed package passed canonical `archive.VerifyFormat`, and the repository
audit passed at index version 166 with 468 active and 719 archived entries. The
shell verifier reports only its already-tracked prefix-order disagreement for
the valid `xhtml-1_1` and `xhtml` sibling paths.

Published SHA-256:

- `org.docbook.docbook-xsl`: `64ca2034399ecf6be8e584aae2b73644cb01ab372a570f180f216178e1e061ec`

## Previous completion: Debugedit 5.3-1

Debugedit tracks authenticated Sourceware 5.x releases from a soft 5.3 floor
and pins Mark Wielaard's complete release-signing fingerprint. The Debian
reference rung ran the entire 58-case upstream suite: 54 passed and four
GDB/DWZ compatibility cases made their expected skips. The native Peios rung
passed all 44 tests applicable to the three shipped tools. Both rungs also
passed clean-rebuild comparison, staged path-rewrite/archive-classifier/CRC
tests, and the package hardening checks.

The final main, common, debuginfo, debugsource, and corresponding-source
packages passed both archive verifiers. The signed repository was audited at
index version 164 with 467 active and 714 archived entries and no problems.

Published SHA-256 values:

- `org.sourceware.debugedit`: `5ed419861d84ef74a86c85068a8bd4b10a2db04b83a6b31603712e7de77df764`
- `org.sourceware.debugedit-common`: `8b7f4d3db5aab314dc1b7518ab3f64b695a7f485f7f6ef8966b1c5a84c9ca3ad`
- `org.sourceware.debugedit-debuginfo`: `3416dfd4c91f99cce50a5d5b1d98defa030c0f4f0ad91b236435cc4de1e43d0a`
- `org.sourceware.debugedit-debugsource`: `17ae576e99ef450b7a7990d29d62bba1357b66b23eeef221a951459572260cd9`
- `org.sourceware.debugedit-source`: `f524d2c6e71d9ca5c984ee0899869563a8491ff88ee194aab94eacbb688e3297`

## Previous completion: GNU tar 1.35-2

GNU tar tracks authenticated stable 1.x releases with a soft 1.35 floor and
the complete Sergey Poznyakoff release-key fingerprint. Because 1.35 remains
the latest signed upstream release, it carries the minimal upstream-derived
fix stack for CVE-2025-45582, CVE-2026-5704, CVE-2026-18508, and
CVE-2026-18477. The final publish produced main, common, debuginfo,
debugsource, and source packages; all passed both archive verifiers and the
repository audit.

Published SHA-256 values:

- `org.gnu.tar`: `1b6ce3f70efb9baf1f9214be3d19ee5a2ffd79575e7f4dda1ac4fbd1d8401bda`
- `org.gnu.tar-common`: `fda4d4b9a5bb33b082b879de628ab7ad4354be7217b3c641a446dab8b542b56e`
- `org.gnu.tar-debuginfo`: `21df3b4d36e55ca8cec40be5d1e155626d0ec613410fb92087f5db6b35669066`
- `org.gnu.tar-debugsource`: `f0dde64a11c9cb2f211018aae74e9ae40162ddeef7745ea8c864c75b2c4b6ec2`
- `org.gnu.tar-source`: `a7e9cd29243dae7f6c8835eadb2a3b277d98383e42fa2b8ce2d0d219dc76210a`

## Worktree guardrail

The main worktree currently contains unrelated edits to `disk-boot`,
`live-boot`, and the `mpc` to `org.gnu.mpc` migration. Preserve them. Perform
package work in isolated worktrees and integrate only reviewed commits.
