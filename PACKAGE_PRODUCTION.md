# Package production campaign

> Temporary task ledger while Acta is unavailable. Move durable work history
> back to the relevant Acta items when service is restored; do not create
> duplicate tasks in the meantime.

## Objective

Work through the 115 campaign recipes in this repository, bringing each to production
standard, validating it on the Debian reference rung and the native Peios
rung, and publishing signed packages to the local `peios` peipkg repository.
The upstream/dependency pass is complete; the first-party pass is now active.
Atrium, authd, build-essentials, coldplug, libpeios, disk-boot, peiosutils,
fsbase, Dynamic Boot, live-boot, peios-install, and the kernel family are
complete. If a package needs a product or architecture decision, record the
question here and continue with the next independent package.

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

- Last fully closed recipe: `org.golang.go` 1.26.5-1, anchored in the catalogue
  at commits `b1abb24`, `7d483c8`, and `13e9547`.
- Completed: **99 / 115** recipes (86.1%).
- Current upstream/dependency pass: **87 / 87** recipes (100%).
- Current first-party pass: **12 / 28 published**, **12 / 28 runtime-closed**.
- Repository after publishing and independently verifying Go 1.26.5:
  index version 217, with 867 active and 1,700 archived entries.
- Signing fingerprint:
  `63977c7be45624999b88bac5aa55ab5280656ee076617a285c87602a0d980602`.

The 87 upstream recipes and twelve completed first-party recipes account for
the 99 completed recipes. The upstream total grew first when exact cbindgen
0.29.2 became a packaged prerequisite for the libpeios ABI gate, and again
when Go became the authenticated native toolchain for first-party services.

## Go toolchain production release: 1.26.5-1

`org.golang.go` is the rolling source-built Go compiler family, following
stable releases from the soft 1.26.1 floor. It bootstraps through the private,
locked Go 1.24.6 seed and fails closed when upstream eventually raises that
floor. The four-package split separates the compiler/tool tree, useful
function-symbol debuginfo, installed standard-library source, and complete
corresponding source.

The native build completed the complete offline-capable standard-library and
`cmd/go` test sets, a real CGO compile/run, independent-root deterministic
compile checks, installed GOROOT checks, and release-policy symbol splitting.
Pekit lint reports zero findings; the documented exceptions are Go upstream's
unsigned source releases and its intentional static ET_EXEC/CET shape. All four
signed artifacts passed the strict container verifier, and canonical archive
plus cryptographic repository verification reports no problems at index 217
(867 active, 1,700 archived).

## Kernel production release: 0.20.1-rc13-2

The delegated `dev.peios.kernel` recipe now publishes forty binary package
definitions plus one generated corresponding-source package from immutable PKM
tag `v0.20.1-rc13`. The kernel, modules, headers, development tree, split debug
payloads, perf/bpftool/cpupower family, thermal tools, Hyper-V and USB/IP tools,
and the smaller in-tree utilities all completed their declared native build
stages using the exact Rust 1.83.0 and LLVM 18.1.8 kernel toolchain lane.

The native root keeps Peiosutils as the system Coreutils implementation and
exposes GNU compatibility tools only below `/usr/libexec/coreutils-build` for
upstream build machinery. It materialises the effective StrataFS `/etc` view in
the disposable build root and records security xattrs instead of attempting to
apply them on the Linux host. The locked release needed two fail-closed outer
recipe corrections: perf receives the Python development interface that
provides `python3-config`, and exactly two reviewed cpupower invocations receive
the private GNU `install` path. The matching source-tree corrections are
retained for the next PKM release.

An earlier partial publication had already consumed revision `-1`; repository
immutability correctly rejected replacement artifacts. The production rebuild
therefore uses one shared catalogue overlay to advance the whole family to
revision `-2`, retaining the old history. All 41 signed artifacts passed the
strict container verifier, and canonical archive plus cryptographic repository
verification reports no problems at index 216 (863 active, 1,696 archived).
Catalogue commit: `fb6cb22`. The matching next-release PKM build-closure fix is
local commit `28aae2f` on `production/kernel`.

## Peios installer production release: 0.3.0-8

`dev.peios.peios-install` is the qualified successor to `peios-install` and
provides/replaces the unqualified identity through 0.3.0-7. Its runtime closure
now names the qualified peiosutils, e2fsprogs, and dosfstools packages plus the
shell and peipkg interfaces it actually invokes. The package ships its MIT
licence and an installed script staged by the build rather than taking an
unchecked recipe-tree file directly.

The audit fixed a real refusal-path bug: negating `part create` before reading
`$?` discarded exit status 3, so a protected existing partition table could
never produce the promised `--force` guidance. A dedicated helper now retains
the original status. Syntax and fixture tests cover block-device discovery,
mounted-device refusal, direct and NVMe partition names, force propagation,
the deliberate-refusal diagnostic, generic partitioning failure, and exact
staged-payload identity. Debian and native Peipkg package rungs both pass.

The signed artifact was published at repository index 206. Full repository
verification reports 820 active and 1,579 archived entries with no problems.
SHA-256: `b961132cd28d779e49ab44d22f66e940970babb3e94ac412b5e412306ac4bd4f`.

## Live-boot production release: 1.0.0-19

`dev.peios.live-boot` and `dev.peios.live-boot-irf` are the qualified main-root
and initramfs halves of live-medium boot. Both retain their old unqualified
names as migration capabilities; the main package pins its IRF sibling at the
exact release and routes it into the declared initramfs root. The IRF package
depends on qualified peiosutils 0.8.5, explicitly requires `sh` and prelude hook
ABI 3, retains the disk-boot conflict, and both packages ship the MIT licence.

The production command line is `loglevel=4 init=/bin/peinit2`: it no longer
forces maximum printk verbosity or an immediate reboot on panic. The root hook
uses prelude's common log format, validates its specialist runtime tools,
diagnoses every load-bearing mount or security-descriptor failure, keeps the
medium move deliberately non-fatal, and has a bounded test seam. Its Debian
host and native Peipkg test runs cover missing tools, discovery exhaustion,
medium selection, the complete squashfs/tmpfs/overlay mount sequence, the
security descriptor, a non-fatal move failure, and a fatal lower-layer failure.

A fresh composed closure placed the main package in `/`, the IRF package and
its complete runtime closure in `boot/initramfs`, and materialised both payloads
and licences. `peios-install` 0.3.0-7 was published alongside it because
uninstall requests target exact installed names; it now removes the qualified
live packages and installs `dev.peios.disk-boot`. All three signed artifacts
passed the strict archive verifier, and the full repository audit at index 205
reported 819 active and 1,578 archived entries with no problems.

Published SHA-256 values:

- `dev.peios.live-boot`:
  `3e150a1c709e576d3b05c6134a893fb52a28e086b2acfc363f593ac25019335a`
- `dev.peios.live-boot-irf`:
  `24192031de3740173b9159b9fa15a2a2948286acb2e1faab9576ccbe30f50721`
- compatibility revision `peios-install`:
  `af7444f7713832dfa7523e867fdafe6eeff618926e20633ee6ca8a7ea5ca8a83`

## LLVM/Rust toolchain transition (2026-09-08)

The exact rolling-Rust publication fix is commit `eec1f31` (`Skip empty Rust
debug companions`) and has been merged into `pkgs/main`, preserving the recipe
reference recorded by the signed packages. The unrelated first-party edits
were restored without conflict after LLVM publication and remain deliberately
uncommitted in the main worktree.

Completed and published:

- `org.rust-lang.rust-stage0-1.82` 1.82.0 and the frozen
  `org.rust-lang.rust-1.83` 1.83.0 kernel lane;
- rolling `org.rust-lang.rust-stage0` 1.97.1 and 1.98.1 at repository indexes
  183 and 184 respectively; and
- current `org.llvm`/`org.llvm.clang`/`org.llvm.lld` 22.1.8 as a 15-package
  runtime, development, static, debug-info, debug-source, and corresponding-
  source family at repository index 185; and
- rolling `org.rust-lang.rust` 1.98.1 as a 10-package compiler, Cargo,
  rustfmt, standard-library, source, debug-info, and debug-source family at
  repository index 186.

LLVM's final native run passed every supported upstream test: LLD passed 2,069
with 1,111 unsupported; Clang passed 44,524 with 5,200 unsupported and 24
expected failures; LLVM passed 36,847 with 33,873 unsupported and 64 expected
failures. There were no unexpected failures. All 15 signed artifacts passed
both `verify.sh` and canonical `archive.VerifyFormat`; full repository
verification reports no problems.

Rust's native self-hosting build and installed compiler, Cargo, rustdoc,
rustfmt, offline-Cargo, licence-closure, LLVM-linkage, hardening, debug/source,
and package-split gates passed. All 10 signed artifacts passed both archive
verifiers, and the repository re-verification at index 186 reports no problems.

Resume order:

1. rebuild and test PKM with its exact Rust 1.83.0 and LLVM 18.1.8 pins; and
2. commit only the validated PKM `pekit.toml` change, preserving unrelated
   `audits/` and `evman/` content.

The temporary toolchain worktree is no longer needed once its build output has
served the PKM validation and may then be removed. The old Rust worktree has a
17 GiB artifact pool containing 2,057 filenames absent from the signed repo and
requires an informed discard decision. The unregistered LLVM worktree remnant
still needs privileged deletion with
`sudo rm -rf -- /home/jack/projects/peios/pkgs-llvm-production.worktree`.

## Peiosutils complete security refresh: 0.8.5-1

`dev.peios.peiosutils` 0.8.5-1 supersedes 0.8.4-1 and completes the current
security pass. Its public source and intentionally unsigned immutable
`v0.8.5` tag are commit `f02265ad1`; catalogue commit `122fd62` locks that
exact commit. The release retains every 0.8.4 fix and adds the two changes
which arrived immediately after that release: cross-device `mv` now follows
the Peios ownership contract and strips set-id bits, and `stdbuf` now uses a
packaged private preload module rather than extracting executable code below
`TMPDIR`.

The resulting 67-advisory inventory is explicit and closed: 26 fixed, 39 not
applicable to Peios, two accepted, and zero todo. The accepted entries are the
low-severity mkdir create-then-SD interval and POSIX uid/gid non-preservation
for cross-device `mv`; the latter is deliberate because destination security-
descriptor inheritance and KACS, rather than POSIX ownership copying, are the
Peios authority. This release therefore contains every agreed security fix
without misrepresenting those two product-level design decisions as code
fixes.

Both the Debian reference and Peios-native clean-room package gates pass,
including release tests, the full multicall build, installed-payload smoke
tests, ELF hardening and ABI checks, split-debug/source checks, and checkout-
path leak checks. Focused cross-device `mv` and external-`stdbuf` tests also
pass. The private preload DSO is installed at the architecture-correct
`/usr/lib/x86_64-linux-peios/peiosutils/libstdbuf.so`; it intentionally has no
`DT_SONAME` because it is loaded privately and no package may link against it.

All five signed artifacts pass the strict container validator, and canonical
archive plus cryptographic repository verification reports no problems at
index 203 (817 active, 1,575 archived). A fresh exact-version compose selects
0.8.5-1 with libpeios 0.5.0, libblkid 2.42.3, glibc 2.44-7, and libgcc
16.2.0-2. Materialization preserves the multicall binary and applet links,
installs the private `stdbuf` DSO at the compiled-in target-triplet path, and
executes the composed `cat` and `dirname` applets through the composed loader.
The corresponding-source package contains `ADVISORIES.toml`, the `mv` and
`stdbuf` sources, and the patched uucore tree.

Published SHA-256 values:

- `dev.peios.peiosutils`:
  `348a79674e2a4da9a0c56cea361284d1b4cd273ae5e85abbc34d19a2aa2accdb`
- `dev.peios.peiosutils-common`:
  `9db773343a033edc211b5575d299ed9560599d37ad8179db7c62155d9ee2d6bd`
- `dev.peios.peiosutils-debuginfo`:
  `8b145b1c28e71d34970bfaf880f1d1b92a535a02b7e0547deee03292c8efc0d3`
- `dev.peios.peiosutils-debugsource`:
  `6aac59457d3fab797506fa5b50591d740d9f6dcff72bd1be0e5129f9895ddd15`
- `dev.peios.peiosutils-source`:
  `24c7f60982732dc53a42ff999454366c02500e9fb13e48eba1c618c93f4d4549`

## Previous Peiosutils security refresh: 0.8.4-1

The complete implemented security pass is now published as
`dev.peios.peiosutils` 0.8.4-1. The source history was rebased cleanly onto the
0.8.3 release so the Dynamic Boot `mkuki --kernel-dir` work remains present;
the public source is commit `b63ff9e`, under the intentionally unsigned
immutable tag `v0.8.4`, and the catalogue locks that exact commit at
`100028c`.

The release carries all 26 fixes from the current 67-advisory audit. Those
include the RustSec dependency updates for `anyhow`, `memmap2`, and
`crossbeam-epoch`; identity- and descriptor-anchored protection for the
root/removal, backup, recursive-copy, attribute-preservation, created-node,
split-output, and tail-follow paths; safe non-truncating touch creation;
private stdbuf preload extraction and TMPDIR validation; and the audited
non-UTF-8, signal, identity, nohup, env, chroot, head, and dd corrections.
`ADVISORIES.toml` records 39 additional advisories as not affecting Peios.
It also keeps two decisions explicit rather than claiming them fixed: the
accepted low-severity mkdir creator-SD exposure interval, and one low-severity
todo concerning POSIX uid/gid preservation during cross-device `mv` (whose
correct interaction with the KACS SD owner still requires a product decision).

All Rust files changed by the security series pass rustfmt, `git diff --check`
is clean, and `cargo check --workspace --locked` passes against libpeios 0.5.0.
The Debian reference and Peios-native rungs both pass their release tests,
complete multicall build, installed-payload smoke tests, ELF hardening and ABI
checks, split-debug/source checks, and checkout/build-path leak gates. The
locked Git-source publication repeated the native build independently of the
local-checkout qualification.

All five signed release artifacts pass the strict `verify.sh` container
validator. `peipkg-repo verify` reports no problems at index 202 (817 active,
1,570 archived), including canonical archive and cryptographic signature
verification. A fresh compose lock selects `dev.peios.peiosutils` 0.8.4-1
together with libpeios 0.5.0, libblkid 2.42.3, glibc 2.44-7, and libgcc
16.2.0-2; materialization preserves the multicall executable and its applet
links, and the composed loader executes the installed `cat` and `dirname`
paths. The corresponding-source package contains `ADVISORIES.toml` and the
patched applet/uucore source trees.

Published SHA-256 values:

- `dev.peios.peiosutils`:
  `74586ef0d3eee7308c73e6e5d2a686c1b4702b72ba6b2bf51f2828062b8f261b`
- `dev.peios.peiosutils-common`:
  `d8b8b50c9b429713168515aa93283e9c1cb62783a11d6e7b15b9a1d321c778e3`
- `dev.peios.peiosutils-debuginfo`:
  `9ed79eefbda3a40812f9baefa03d94df6d398ad792a8f09c210560ef6d4614c8`
- `dev.peios.peiosutils-debugsource`:
  `5ac661d38356ecb695d8bf0a2416c2d1bd942c4c9cd40d143ce7d91697edd0f9`
- `dev.peios.peiosutils-source`:
  `861fa8378b213bcc547ba217d234dc0a909fb624f3840e1486404d3e0c5ac853`

## Previous first-party completion: Dynamic Boot 1.0.0-1

Dynamic Boot is now a production-qualified feature package:

- `dev.peios.feat-dynamic-boot` carries the `dynamic-boot` lifecycle and
  intentionally provides/replaces the former unqualified package;
- `mkuki --kernel-dir /usr/lib/modules` resolves exactly one
  `<release>/vmlinuz-*` image before every build and recursively watches the
  kernel tree, so replacing a release directory upgrades the UKI without
  reinstalling the feature;
- the UKI service selects `/lcl/etc/boot/cmdline` at startup and retains the
  live-image `/usr/share/live-boot/cmdline` as its explicit fallback; and
- the initramfs watcher excludes `var/state/peipkg` and `lcl/conf/peipkg`, in
  line with the installer and Peiso's production image boundary.

The required applet change is public in peiosutils commit `82ad66e`, released
under the intentionally unsigned immutable tag `v0.8.3`; the catalogue locks
that exact commit at `3b4a5ba`. Debian and Peios-native builds both passed the
focused `mkuki` unit and CLI suites, including a real watcher test that replaces
the release directory and observes the new kernel in the rebuilt UKI. Both
environments also passed the feature's mocked registry/lifecycle and command-
line-selection tests. The clean release build retained peiosutils's complete
installed-payload, split-debug, hardening, path-leak, and package-family gates.

All six signed artifacts pass the strict shell validator. Full repository
verification, including canonical archive and signature checks, reports no
problems at index 199. A fresh independent compose lock selects
`dev.peios.peiosutils` 0.8.3-1 and closes the feature through libpeios, Dash,
libblkid, glibc, and libgcc; materializing that lock preserves the executable
watch launcher and the `mkuki` multicall link.

Published SHA-256 values:

- `dev.peios.feat-dynamic-boot`:
  `1aa9637bae1f93e6619323b8d1f4c46d18caf92b4a167418a00f54cd2dee073f`
- `dev.peios.peiosutils`:
  `0cb7432d9743b02a50c188ad616fd1941819592547af0bae673209bd6056bd7c`
- `dev.peios.peiosutils-common`:
  `80169b0557c18d5e3dcd1064bf5fd4fe81a26d39966ba4ea70f17b7d4f7dc8ba`
- `dev.peios.peiosutils-debuginfo`:
  `2cb1ea09acd12b5bfb5d365dcf06aa80b5263d522042caeae4e2f88ce8e1b691`
- `dev.peios.peiosutils-debugsource`:
  `1b7b7cfd1213064fc7cc95a86cd2b2502f207f3d4e3d9c743d46ecd077ee2127`
- `dev.peios.peiosutils-source`:
  `8dbc773c0c83cf6b392086cd721067c0e9c9753793a012f4ea77c69283f8911b`

## Previous first-party completion: eventd 0.1.0-10

Eventd is now published as a production family rather than its former
unqualified monolith:

- `dev.peios.eventd` owns the critical daemon, inert configuration and service
  seeds, regman policy, and protected empty state-directory skeleton;
- `dev.peios.evctl` is an independently installable native query client;
- each ELF has its own debuginfo package;
- one noarch debugsource package covers their shared Rust source graph; and
- `dev.peios.eventd-source` carries the exact public Git release and packaging
  controls.

The main package depends on the exact matching evctl package so migration from
the old monolith cannot silently remove the client, while evctl remains usable
without installing the service. Both qualified runtime boundaries carry the
appropriate legacy replacement metadata through `eventd` 0.1.0-9. The service
also declares its non-ELF dependency on the production authd authority.

The source is public at `https://github.com/peios/eventd`, commit `0521f34`,
with the intentionally unsigned immutable tag `v0.1.0`; the catalogue locks
that commit at `d809d9c` and moves the recipe to `dev.peios.eventd`. The release
replaces mutable sibling `peios-rs` paths with the reviewed exact public commit
`f4309f7`, vendors the complete Cargo.lock graph, and compiles offline against
the packaged libpeios 0.5 ABI using rolling Rust 1.98.1 and LLVM 22.

The native package build and the independent test target each passed all 105
Rust tests. Installed-payload gates validate evctl dispatch and versioning, the
six mandatory configuration paths, the exact `/usr/sbin/eventd` service image,
SYSTEM/critical/authd service policy, empty mutable stores, regman delivery,
PIE, full RELRO, BIND_NOW, NX stack, libpeios SONAME linkage, split-debug
integrity, and absence of checkout/build path leaks. All six signed artifacts
pass the strict shell verifier and canonical package parsing/resolution. Full
repository verification at index 197 reports 810 active and 1,548 archived
packages with no problems.

Published SHA-256 values:

- `dev.peios.eventd`:
  `bd442bb8812d3f6421067af59c25810e24c0bfe929bacf28a15547d91b610bab`
- `dev.peios.evctl`:
  `92f9af8e6988d55a8b86567a16ce372f9f0fd24e57360d11bcd730de8875da1d`
- `dev.peios.eventd-debuginfo`:
  `69d9f0d787cdfbf8f4184297a993ebb2e75cdb74a53b5aee0c71a4976066c2cd`
- `dev.peios.evctl-debuginfo`:
  `d777ed3d533709ddbaed365b48ec00ab30dbd36e8f78f8b33fbda1c7710e0468`
- `dev.peios.eventd-debugsource`:
  `24ff6b829b6c1f297801088586e83dd0e68d1b216379f2c27af05604bcf907a4`
- `dev.peios.eventd-source`:
  `78c0358167763234d5ddef2f576dbeed6bd824572abb19c5ccc8735e290862c2`

## Gettext 1.0-2 glibc 2.44 compatibility refresh

GNU Gettext remains on the newest stable upstream release, 1.0. Its package
revision 2 replaces the runtime dependency on GNU Coreutils with
`dev.peios.peiosutils`, while the native build uses the private GNU
build-compatibility path where upstream's test harness requires GNU-only
interfaces.

The refresh backports upstream Gnulib commit `ca635799`, which changes the
`posix_spawn_file_actions_addchdir` probe from a link check to a declaration
check. Without that fix, glibc 2.44's redirected declaration causes Gettext's
bundled fallback object to define the `_np` symbol as a jump to itself and
three Gnulib tests spin indefinitely. With the exact backport, all 672 main
tests, 14 system tests, and the bundled Gnulib suites complete without a
failure or deadlock.

All nine signed artifacts passed `verify.sh` and canonical trust-aware archive
verification. Full repository verification at index 214 reports 822 active
and 1,614 archived entries with no problems. Catalogue commit: `a78d3b1`.

## Remaining current-pass recipes

The native `dev.peios.kernel` and `org.golang.go` families are complete.
Peinit 0.0.2, Loregd 0.21.6, and Prelude 0.0.3 are committed and tagged
locally with production package splits; their remote locks wait for explicit
approval to publish the source commits and tags. Prelude's remaining native
build prerequisite, the Rust musl standard-library target, is being packaged.
Resolvd's complete local production split is committed. Netd's matching local
production family is source-committed and package-validated; both now share one
exact Peios Rust revision. Their immutable top-level release graphs wait on
public Resolvd and Netd repositories. Trustd and Timed are active production
lanes. `mockinit` needs a catalogue-disposition choice; `peios-dwe` and
`peios-kernel-only` explicitly forbid public publication.

## Deferred first-party recipes

`loregd`,
`mockinit`, `netd`, `peinit`, `peios-dwe`,
`peios-kernel-only`, `peipkg`, `pnpd`,
`prelude`, `resolvd`, `timed`, and `trustd`, plus the already-qualified
`dev.peios.oobe` and `dev.peios.peios-installer` recipes.

## Follow-ups and known blockers

- `loregd` cannot meet the native-rung acceptance gate until Peios has a Go
  toolchain package. Its current module requires Go 1.26.1, while the signed
  package pool contains no Go compiler at all; the existing recipe therefore
  builds only by inheriting the host toolchain and undeclared network module
  downloads. Productionisation needs an authenticated, bootstrapped Go recipe,
  then a vendored/offline build plus runtime, debuginfo, debugsource, and source
  packages. The source checkout was deliberately left untouched: it is two
  commits ahead of `origin/main` and also contains uncommitted logging/package
  edits associated with the peinit Phase-1 relay change.
- `mockinit` is explicitly a throwaway, pre-peinit PID-1 stand-in. Publishing
  it as a production runtime would preserve temporary service and security
  assumptions that the real peinit has replaced. Decide whether to delete it
  from the public catalogue or retain it under a clearly test-only identity.
- `netd` is locally productionized at source commit `7e258e4`. Its five-package
  runtime/debug family passed 87 release tests, strict Clippy, two independent
  deterministic builds, installed service/profile/state/manual gates, exact
  split-debug/source validation, complete licence collection, and native
  Peipkg hardening checks. Mutable peios-rs, libpeios, and PKM sibling fallbacks
  are gone: the two Rust sources are exact public revisions and native builds
  consume `dev.peios.libpeios-devel` 0.5.0. The source checkout still has no
  remote or immutable release tag, so the catalogue intentionally remains
  local-only until a public provenance home exists.
- `peios-dwe` and `peios-kernel-only` are intentionally non-public recipes.
  The former grants unauthenticated SYSTEM access for a DWE guest and its own
  security policy forbids repository publication; the latter is a kernel
  conformance fixture with no init or userspace. Keep both available to their
  controlled image/test workflows but out of the public repository.
- `peios-experimental` carries an existing uncommitted 0.3.0-9 trust-floor
  correction in the main worktree. Preserve it and defer the edition audit
  until that concurrent change is ready to incorporate.
- `peipkg` is also blocked on the authenticated Go bootstrap. The clean public
  source requires Go but the native signed pool has no Go compiler, so its
  current package can only be reproduced with an undeclared host toolchain.
  Once Go is packaged, release the source from a new immutable version and
  split the static `peipkg` consumer, `peipkg-compose` image builder, and
  `peipkg-repo` publisher/verifier into independently installable packages,
  with conventional debug and corresponding-source companions.
- `pnpd` has no source remote or release tags, and its existing recipe falls
  back to undeclared sibling peios-rs, libpeios, and built PKM header trees.
  Give the PNP source repository a public provenance home before replacing
  those fallbacks with immutable Rust inputs and the packaged libpeios/kernel
  development interfaces.
- `prelude` is locally release-ready at source commit `2d44ae6`, unsigned tag
  `v0.0.3`, and catalogue commit `1281f38`. It has a vendored offline source
  graph, static musl PIE runtime, per-family debug/source split, 40 passing
  tests, deterministic rebuild checks, and zero unwaived production-lint
  findings. Publish the source commit/tag, lock it, and run the native package
  rung once the packaged Rust musl standard library is available.
- `resolvd` is locally productionized at source commits `7dd3e63` and
  `ec7da6f`, and catalogue commit `e485d26`: 41 tests, strict Clippy, hardened
  daemon/client/NSS splits, debug/source payloads, and migration metadata pass.
  Its direct Peios binding now shares libnetd's exact public revision, so the
  combined graph contains one `peios-sys` with `links = "peios"`. Publication
  still waits on public Resolvd and Netd repositories so the remaining local
  libnetd edge can become an immutable Netd revision.
- `timed` and `trustd` are active local productionization lanes. Neither has a
  configured public source remote or immutable release tag, so publication will
  still require an explicit provenance home after their local gates pass.
- `dev.peios.oobe` and `dev.peios.peios-installer` are already qualified by
  name, but both build from the same local-only `installer` checkout and its
  sibling path dependency on the local-only `msip` repository. Neither source
  repository has a remote or immutable release tags. Publish and pin both
  source graphs before auditing the daemon/UI/package splits and releasing
  them.
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
- Authd's and coldplug's previously open `libpeios.so.0` closure edges are now
  closed by `dev.peios.libpeios` 0.5.0-1. A clean compose lock containing both
  top-level products resolves the qualified runtime in the anchor and named
  initramfs roots.
- The pre-baseline peiosutils/libpeios runtime break is closed by
  `dev.peios.peiosutils` 0.8.2-1. The signed-repository disk-boot closure picks
  it instead of legacy `peiosutils` 0.1.4-15, binds it to
  `dev.peios.libpeios` 0.5.0-1, and passes the installed-root applet smoke. The
  deliberately omitted ambiguous `peios_token_session_id` C export remains
  absent.
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
- `dev.peios.build-essentials-c` 1.0.0-6 now depends on canonical toolchain
  packages throughout. The former virtual-name Binutils edge could select
  legacy `binutils` alongside GCC's canonical dependency and make pristine
  build-root composition fail on overlapping `/usr/bin` payloads.
- GCC 16's packaged `libstdc++.so.6` emits "no version information available"
  for C++ consumers in the native root. Current programs still link and run,
  but the missing GLIBCXX/CXXABI symbol-version surface needs a focused ABI
  audit before the toolchain is considered fully production-complete.
- Rust now has disjoint package-source lanes: the retained exact 1.83.0 recipe
  (with exact 1.82.0 stage0 and LLVM 18 dependencies) is the kernel toolchain,
  while the rolling recipe follows stable releases from a soft 1.98.1 floor.
  LLVM 22 likewise has a separate rolling recipe so publishing a current
  userspace compiler cannot move Kbuild. Current LLVM 22 and Rust 1.98.1 are
  published; the final frozen-kernel rebuild remains outstanding.
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
- Package-campaign cleanup removed every per-recipe `out/` cache and 19 stale
  registered `pkgs` worktrees after confirming that each carried no unique
  tracked patch. After the LLVM/Rust transition, another approximately 237 GiB
  of reproducible LLVM 22 and Rust/stage0 working output was pruned from the
  main catalogue and temporary toolchain worktree. The one retained Rust
  worktree contains an old 17 GiB package pool with 2,057 filenames absent from
  the signed repository and therefore needs an explicit discard decision
  rather than being treated as an ordinary build cache. The remaining 8.4 GiB
  in the unregistered LLVM worktree needs interactive privileged deletion
  because its build namespace left files owned by another uid.

## Latest first-party publication: fsbase 1.0.0-10

The base-filesystem family is now published as `dev.peios.fsbase`,
`dev.peios.fsbase-irf`, and `dev.peios.fsbase-stratafs-mount-hooks`, anchored
at catalogue commit `d3af9c4`; the public package-name documentation is learn
commit `e5edc26`. The first package owns the main-root skeleton and the
protected `/home` and `/tmp` security descriptors; the second owns the smaller
independently executing initramfs skeleton; the third owns the two inseparable
hooks that mount the matching StrataFS view graph in those roots.
Keeping the hooks separate from the skeletons preserves the option to compose
the filesystem layout without selecting StrataFS, while keeping both hooks in
one package prevents their common view policy from drifting.

The three identities provide their former unqualified names and replace those
packages through 1.0.0-9. They carry explicit homepage, architecture, licence,
and migration metadata, and each binary package ships its MIT licence. The
hook package now depends directly on `dev.peios.peiosutils` from the 0.8.2
baseline and on Prelude hook ABI 3. The previously pending console-format
change is complete, including correction of an interrupted edit that printed
an `OK` line before the mounted-root mount had actually succeeded.

The new suite fixes and exercises the main/initramfs directory split, the
psABI `/lib64` links, all sixteen exact StrataFS mount calls, canonical paths
inside the mounted-root chroot, absolute test-root isolation, and successful
and failed mount reporting. It passes on both the Debian and native Peios
rungs. A clean compose places both hooks and their qualified runtime closure
under `boot/initramfs`, reproduces exactly the two intended `/home` and `/tmp`
security-descriptor records, and confirms that installed hook bytes match the
tested sources.

All three signed packages pass `verify.sh` and canonical repository format and
signature verification. A repository-only compose requested the three legacy
names and resolved each to its qualified 1.0.0-10 provider. The corresponding
old flat-pool artifacts were moved recoverably to
`_pkgsOut_/archive/reverse-dns-migrated/`, and both native build-root generators
now seed `dev.peios.fsbase` directly. Publication is repository index 196, with
804 active and 1,542 archived entries; full repository verification reports no
problems. Published SHA-256 values:

- `dev.peios.fsbase`:
  `3db3e469b86d63ae9df6dea2bb8e6b1673e3c20b7a04e844d5cec4656d2737c3`
- `dev.peios.fsbase-irf`:
  `ed44b05fa7b423214fcf09df527ebdbb4a2b5421b16521951672b30227a4b18a`
- `dev.peios.fsbase-stratafs-mount-hooks`:
  `c755c60485c11a725925b4c622f017e2e468a834ca1bc1cff7fa6507bca3a230`

## Previous first-party publication: peiosutils 0.8.2-1

Peiosutils is now published as `dev.peios.peiosutils`,
`dev.peios.peiosutils-common`, `dev.peios.peiosutils-debuginfo`,
`dev.peios.peiosutils-debugsource`, and `dev.peios.peiosutils-source`, anchored
in the catalogue at commit `0bcaf47`. The upstream source is public at
`https://github.com/peios/peiosutils`, commit `fb0d002`, with the intentionally
unsigned immutable tag `v0.8.2`. The catalogue follows immutable release tags
from a soft 0.8.0 production floor and retains locks for 0.8.0, 0.8.1, and
0.8.2.

The release removes the undeclared sibling-tree build bridge: all Cargo and
Git dependencies are vendored from the locked source graph, and the Rust
toolchain archive is checked by SHA-256 and its upstream signature. Signature
verification is hermetic in both build roots: it dearmors the shipped public
key into a local keyring, verifies with `gpgv`, and requires the complete
`VALIDSIG` fingerprint without starting or depending on a persistent GPG
agent. The runtime package depends on the qualified current `libpeios.so.0`
provider and `org.kernel.libblkid`, provides the legacy `peiosutils` capability,
and replaces the old development package through 0.1.4-15.

All 91 targeted tests pass in both the Debian reference build and the native
Peios build, including the token interactivity compatibility gate. The five
clean-release artifacts pass `verify.sh` and canonical `archive.VerifyFormat`;
their manifests record source commit `fb0d002` and clean recipe commit
`0bcaf47`. Publication is repository index 195, with 801 active and 1,539
archived entries, and a full `peipkg-repo verify` reports no problems.
Published SHA-256 values:

- `dev.peios.peiosutils`:
  `6b919b2935af3a397b20ae7b244abf4d6901f810e5a9e070971719647629e999`
- `dev.peios.peiosutils-common`:
  `e8e22194550ed28537f149875561a5a1e47ec53185fc1f3f68be6d800290c89b`
- `dev.peios.peiosutils-debuginfo`:
  `66ee84c0834ec9730d7da4e561ee4e718f8fa0d819b26b1f406a3ddfcec71946`
- `dev.peios.peiosutils-debugsource`:
  `863fd6b74c5726cefadfedbb432a2e7b698b3791402600afcc8c239b7a007de3`
- `dev.peios.peiosutils-source`:
  `21421d95f2b086fc0ae4c2cc6e4bf020a55087d66d83385d9a3311ef0fa212f2`

The published-only disk-boot closure now resolves
`dev.peios.peiosutils` 0.8.2-1 into `boot/initramfs` together with
`dev.peios.libpeios` 0.5.0-1. Its own dynamic loader reports every dependency
from that composed root, and `cat`, `dirname`, `mktemp`, `lsblk`, `mount`, and
`sleep` all execute successfully. This closes the runtime gate that held
disk-boot open.

## Previous first-party publication: disk-boot 1.0.0-10

The installed-system boot family is now published under
`dev.peios.disk-boot` and `dev.peios.disk-boot-irf`, anchored in the catalogue
at commit `5782669`; public boot documentation is commit `77b4480`. The main
package owns the install-time cmdline template and has an exact cross-root
dependency on the same-release initramfs hook. The hook declares
`default_root = "initramfs"`, conflicts symmetrically with `live-boot-irf`,
and retains `disk-boot` / `disk-boot-irf` migration capabilities while
replacing the unqualified family through 1.0.0-9.

Revision 10 includes the already-published PEI-782 cmdline change
(`loglevel=4`, no `ignore_loglevel`) and completes the production pass with
an explicit shell dependency, peiosutils 0.1.4 floor, prelude hook ABI 3,
shipped MIT licence text, shared boot-console outcome logging, literal kernel
argument handling, and explicit mount-failure attribution. The existing
optional-fsck policy is unchanged: journal replay remains the baseline, status
1 is accepted after an automatic repair, and any status above 1 stops before
mounting.

The behavioural suite covers ten paths: invalid test-root isolation, missing
runtime tools, missing and unsupported root specifications, last-root-wins tag
resolution, glob-looking tag data, bounded discovery retries, corrected and
failed fsck results, and mount failure. ShellCheck, direct Dash execution, the
Debian package-root test, and the native Peios package-root test pass. Both
packages pass `verify.sh` and canonical `archive.VerifyFormat`; their published
pool and repository copies are byte-identical. A compose lock places only the
IRF half and its closure in `boot/initramfs`, and a negative lock correctly
rejects it alongside `live-boot-irf`. After the eighteen old loose development
artifacts were moved recoverably to
`_pkgsOut_/archive/superseded-disk-boot-development/`, the legacy `disk-boot`
goal also resolves to the qualified provider.

Repository publication is index 193 (796 active, 1,533 archived), and full
repository verification reports no problems. Published SHA-256 values:

- `dev.peios.disk-boot`:
  `2cb5ed50e2b526af7a6d3bc30a88606130499d12c3079fd3b6908a78dac0f944`
- `dev.peios.disk-boot-irf`:
  `94824abf3c085f482d6236b50cb5b3f8c2e3b8e2d38323b1c6d0fabcae0ae680`

The original native harness exposed that published `peiosutils` 0.1.4-15 had
an undefined reference to the removed pre-baseline
`peios_token_session_id` export, so the recipe was published but held open.
That gate is now closed: a repository-only compose selects
`dev.peios.peiosutils` 0.8.2-1 and `dev.peios.libpeios` 0.5.0-1 in the named
initramfs root, and the packaged `lsblk`, `mount`, `cat`, `dirname`, `mktemp`,
and `sleep` applets execute successfully through the composed loader.

## Previous first-party completion: libpeios 0.5.0-1

libpeios is now the first published, qualified Peios C ABI baseline. The
source is public at `https://github.com/peios/libpeios`, commit `4e71047`, with
the intentionally unsigned immutable tag `v0.5.0`; the catalogue locks that
exact commit at `4734895`. Earlier 0.3.4 development packages carried no
compatibility promise and are not treated as an ABI baseline. Starting here,
compatible additions retain `libpeios.so.0`, while incompatible changes
require an explicit SONAME decision.

The family is split into `dev.peios.libpeios`, `-devel`, `-static`,
`-debuginfo`, `-debugsource`, and generated `-source` packages. The development
package pulls the exact runtime plus `kernel-headers`, because its public
headers deliberately expose the matching `<pkm/*.h>` UAPI. Qualified packages
provide and replace the old unqualified 0.3.4 names through revision 8. Forty
loose, unpublished 0.3.4 development artifacts were moved recoverably to
`_pkgsOut_/archive/superseded-libpeios-development/`; signed repository history
was untouched.

The production pass also aligned libpeios with the current public PKM UAPI at
commit `b5519e6`: LogonSession LUIDs and interactive-environment scopes are no
longer conflated, obsolete ambiguous compatibility exports were excluded from
the first baseline, and socket constants now come from the locked UAPI rather
than local numeric mirrors. Public SDK documentation was updated at learn
commit `3046f55`.

Both the Debian reference rung and native Peios rung passed all 256 Rust tests,
dynamic and static installed-consumer smokes, SONAME/full-RELRO/BIND_NOW/NX
stack/no-rpath checks, split-debug and debug-source validation, and checkout-
path reproducibility gates. The native rung uses packaged
`org.mozilla.cbindgen` 0.29.2 to regenerate the committed ABI snapshot exactly;
205 function signatures, 26 public struct layouts, two data symbols, and all
207 DSO exports agree. Every one of the six signed packages passed both
`verify.sh` and canonical `archive.VerifyFormat`; the published flat-pool copies
are byte-identical to those verified outputs. Full repository verification at
index 192 reports 794 active and 1,531 archived packages with no problems.
Authd and coldplug now resolve through the published `libpeios.so.0` provider.
The conservative package `recipe_ref` is `4734895+dirty` because Pekit observes
unrelated boot recipe work still present in the catalogue; the libpeios paths
match the recorded commit exactly.

Published SHA-256 values:

- `dev.peios.libpeios`: `55300ffc022b0cbb09cb0fd5ebce7a934f46275c5f90b6f91f51fa3b10504d03`
- `dev.peios.libpeios-devel`: `0f730c6bdb48af86170c9b76b1f014875a739dab9a3cf59358b51596dc47b3b9`
- `dev.peios.libpeios-static`: `27fed75b4dc34568d8222c1f9f1ca886c2f86d62d42a30fca02d5c3112b1eb5b`
- `dev.peios.libpeios-debuginfo`: `fcf4f3caabbfacc2b4d74b145feff402b1e393325eba414ae5063608046af403`
- `dev.peios.libpeios-debugsource`: `11b49b0d49f37505e5c8e4946ac830ac1b051a5dd1a1c7f48c4e9e2425ddeedf`
- `dev.peios.libpeios-source`: `0f65f38215e79992aac12862c557fa199394a13f4392f9074da832c038cde34c`

## Previous first-party completion: coldplug 1.0.0-3

Coldplug is intentionally one initramfs-only package,
`dev.peios.coldplug-irf`: eudev owns real-root enumeration and hotplug, so a
second daemon or real-root package would duplicate ownership. The qualified
package provides `coldplug-irf = 1.0.0-3` and replaces legacy revisions through
1.0.0-2. Its direct runtime closure names kmod, peiosutils, the Prelude hook ABI,
and `sh`; the kernel module set remains an image-specific concern rather than a
dependency of the hook.

The production pass fixed two behavioural defects. An empty modalias set now
returns Prelude's declined status 69 rather than falsely reporting success, and
shell pathname expansion is disabled while expanding modalias values so kernel
wildcards reach modprobe literally. Driver-change snapshots now use a private
`mktemp` directory with trap cleanup instead of predictable files in `/tmp`.
The test-only root indirection is inert in production because Prelude launches
hooks under an explicit minimal environment.

The six-case shell suite covers absent modprobe, absent module trees, empty
modalias sets, deterministic deduplication with literal wildcards, newly loaded
module reporting, and non-fatal per-alias modprobe failures. It passes directly,
under ShellCheck, through the Debian reference profile, and through the native
Peios profile. Both profiles package successfully. The payload contains only
the hook and its MIT licence; compiled debug, development, source, or separate
documentation packages would be empty or inappropriate initramfs bloat.

The recipe is anchored at catalogue commit `727d94f`; its conservative
`recipe_ref` has a `+dirty` suffix because unrelated boot recipes remain edited
in the same catalogue, while the coldplug paths themselves match the commit.
The signed artifact passed `verify.sh` and canonical `archive.VerifyFormat`.
Full repository verification at index 190 reports 784 active and 1,521 archived
packages with no problems. Public documentation was updated at learn commit
`70f0bb2`.

## Previous first-party completion: build-essentials 1.0.0-6

The distribution-owned build policy is now a four-package stack:

- `dev.peios.build-essentials`: the compiler-free shell and essential
  userland baseline;
- `dev.peios.build-essentials-c`: GCC C, Binutils, glibc and Linux UAPI
  development surfaces, Debugedit, and Patchelf;
- `dev.peios.build-essentials-c++`: the C floor plus the matching GCC C++ and
  libstdc++ development surfaces; and
- `dev.peios.build-essentials-rust`: the C floor plus the complete rolling
  Rust toolchain. The kernel continues to use its separate exact Rust 1.83
  lane.

All concrete implementation edges now name canonical packages and carry
reviewed minimums; only the Linux UAPI deliberately remains a versioned role.
The GCC-family edges remain bounded below major 17, and the rolling Rust edge
below major 2. Exact sibling constraints keep one policy-family revision
together. The three old unqualified names are versioned migration roles with
`replaces` metadata; clean resolution of each legacy goal selects its
`dev.peios` provider. The recipe remains primary-architecture policy despite
its documentation-only payload because the closure deliberately selects that
architecture's compiler. Each package now includes its operator README and MIT
licence text. Debug, development, and corresponding-source companions would be
empty and are intentionally omitted.

Both Debian-profile and native-profile packaging passed. Clean composition of
the baseline produced all promised tools and documentation. C, C++, and Rust
closures resolve completely with the existing signed kernel-header artifact;
pristine native Peios roots then compiled and linked C, compiled and ran a
C++23 program, and compiled and ran a Rust 2024 program with Rust 1.98.1. The
only public-repository closure gap is the already-known unpublished
`linux-kernel-headers` provider, not a missing build-essentials dependency.

The sourceless recipe is anchored at catalogue commit `0f577be`; publication
used the explicit sourceless-provenance allowance, while `recipe_ref` records
that commit. Its conservative `+dirty` suffix observes unrelated boot work in
the whole catalogue, and the build-essentials paths match the commit exactly.
All four signed artifacts passed `verify.sh` and canonical
`archive.VerifyFormat`. Full repository verification at index 189 reports 783
active and 1,520 archived packages with no problems.

## Previous first-party completion: authd 0.0.14-1

Authd is packaged as five independently deployable trust and client boundaries,
with a sixth policy payload kept out of the production daemon package:

- `dev.peios.authd`: the authentication authority;
- `dev.peios.authd-lpsd`: the local principal source daemon;
- `dev.peios.authd-lps`: its administrative client;
- `dev.peios.authd-login`: the login client;
- `dev.peios.authd-nss`: the NSS client module; and
- `dev.peios.authd-live-account`: the explicitly selected, noarch live-image
  administrator bootstrap policy.

The live account split prevents a credential-free administrator bootstrap from
silently entering production installations with `lpsd`. Runtime packages carry
intentional legacy `provides`/`replaces` metadata. Each ELF component has its
own debug-info package, while the family has one shared debug-source package and
one generated corresponding-source package. There is intentionally no `-devel`
package because authd installs no public headers or link interface.

The source release pins both `peios-rs` and `libauthd` inputs to publicly
fetchable exact Git commits, vendors its complete locked Cargo closure in the
networked source stage, and compiles and tests offline with rolling Rust 1.98.1
and LLVM 22. All workspace tests and installed-payload gates pass, including
the authority and principal-source behaviour, refused-login path, NSS SONAME
and exported symbol, registry JSON, and shell syntax. Every ELF passes PIE,
full RELRO, BIND_NOW, NX-stack, RELR, build-ID, no-rpath, split-debug,
debug-source, and checkout-path-leak checks. The generic Debian rung cannot
supply the Peios `libpeios-devel` build contract; substituting its exact public
source then reaches Debian's obsolete Rust 1.85 compiler, below this release's
declared Rust 1.98.1 floor, so native Peios is the authoritative supported rung.

The completed source is public at `https://github.com/peios/authd`, commit
`3386525`, with intentionally unsigned immutable tag `v0.0.14`. The catalogue
locks that exact commit at `d1fd1f7`. All thirteen signed artifacts passed both
`verify.sh` and canonical `archive.VerifyFormat`. Full repository verification
at index 188 reports 779 active and 1,516 archived packages with no problems.
Their conservative `recipe_ref` carries `+dirty` because Pekit observes the
whole catalogue worktree; the authd recipe and release-integration paths match
the recorded commit byte-for-byte, and the dirt belongs to unrelated boot work.
Clean-root resolution correctly reaches the outstanding first-party
`libpeios.so.0` provider gap recorded above.

## Earlier first-party completion: Atrium 0.0.25-2

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
- generated `dev.peios.atrium-source` corresponding source.

Events, Networking, and Principals are explicit placeholder applications and
are excluded from the production payload. There is intentionally no `-devel`
package: the browser SDK is embedded in the runtime and Atrium installs no
public headers, link libraries, or standalone build interface. The old
monolithic `atriumd` package is migrated through the default product's
`provides`/`replaces` metadata. The Terminal package carries the matching
xterm.js/addon-fit MIT notice as well as Atrium's own licence.

The complete host-toolchain and native Peios package gates pass: all five Rust
tests, including the peinit descriptor/pidfd test, and an installed-payload
smoke spanning the daemon/server/session boundary, authentication relay,
cookie lifecycle, catalogue and asset serving, traversal rejection, and
logout. Atrium now pins `peios-rs` and `libauthd` to publicly fetchable exact
Git commits, vendors the complete `Cargo.lock` closure in the networked source
stage, and compiles/tests it offline under rolling Rust 1.98.1 and LLVM 22.
All three binaries pass PIE, full RELRO, BIND_NOW, NX-stack, RELR, build-ID,
no-rpath, split-debug, debug-source, and checkout-path-leak checks. All nine
signed binary/meta artifacts pass both `verify.sh` and canonical
`archive.VerifyFormat`; `peipkg-compose` accepts their canonical format,
resolves their complete current dependency closure, and materialises exactly
the five production apps and three Atrium executables. The hermetic source
transition began at Atrium commit `80f206e`; the completed debug-source release
is public at `https://github.com/peios/atrium`, commit `864c9d1`, unsigned tag
`v0.0.25` by decision. The catalogue locks that exact commit at `6447430`. All
ten signed artifacts, including `dev.peios.atrium-source`, passed both archive
verifiers and were published at repository index 187; full repository
verification reports no problems.

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

The main worktree currently contains unrelated edits to `peios-experimental`
and the active kernel catalogue integration. Preserve them. The pre-existing
live-boot edits were saved as `preserve pre-production live-boot edits` before
the reviewed production commit was integrated; their behaviour and rationale
are represented in the release above. Continue package work in isolated
worktrees and integrate only reviewed commits.
