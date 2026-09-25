# Peios package catalogue

This repository is the source of the packages published by Peios. A recipe is
production-grade only when it can follow upstream releases unattended, build
from declared inputs in clean environments, produce a deliberate package
split, pass tests against its installed payload, and publish signed artifacts
without relying on state from a developer's checkout.

This document is the packaging policy and review checklist. The root
[`lint.pekit.toml`](lint.pekit.toml) enforces the mechanical parts. A local
`lint.pekit.toml` may explain a genuine exception, but it does not lower the
quality bar. Work in progress and its history live in Acta (the production
campaign is PEI-607), not in this repository.

## Repository layout and inheritance

Each immediate subdirectory containing `pekit.toml` is a workspace member. Its
directory name is the recipe's primary reverse-DNS identity. A normal recipe
contains:

```text
org.example.product/
├── pekit.toml
├── pekit.lock
├── package.pekit.toml
├── org.example.product-devel.package.pekit.toml  # when split
├── lint.pekit.toml                               # only for justified exceptions
├── keys/                                         # public verification keys only
├── patches/
│   ├── series
│   └── 0001-example.patch
└── src/                                          # only literal, maintained inputs
```

The workspace files are intentional shared policy:

- [`workspace.pekit.toml`](workspace.pekit.toml) defines membership,
  distribution compiler/linker flags, Rust release settings, and symbol-version
  derivation.
- [`package.pekit.toml`](package.pekit.toml) supplies the signed Peipkg
  repository publication target.
- `_pybuild_/` (Python wheel installation) and `_pkgtools_/` (`split-debug`,
  `collect-rust-licences`, `install-manpages.py`, `config-sub-peios.sh`, and
  `pty-drive.c`, a small send/expect driver for interactive terminal gates) are
  shared helpers every recipe reaches through `$PEKIT_WORKSPACE_ROOT`.
  `dev.peios.packaging-tools` ships `split-debug` and `collect-rust-licences`
  under `/usr/libexec/peios-packaging/` for first-party repositories, which also
  build outside this workspace. `_peiroot_/` and `_debroot_/` prepare the
  native and Debian roots.
- [`env.pekit.toml`](env.pekit.toml) is the default environment: every target
  runs in a clean native root composed from the signed repository, and only
  `build:vendor` gets network access. `debian.env.pekit.toml` (`--env debian`)
  is the Debian root for the `minimal-bootstrap` seed only.
- [`lint.pekit.toml`](lint.pekit.toml) is inherited by every member.

Do not copy those settings or environment links into individual recipes. A
recipe may override a workspace default only when the upstream build genuinely
requires it, and must explain why beside the override. Merge precedence is
workspace defaults, delegated source, then member recipe.

Generated build trees, caches, downloaded archives, package artifacts, private
keys, composed roots, and temporary worktrees do not belong in this repository.
Keep them under ignored `out/` or workspace operational directories. Do not
leave obsolete pre-qualification directories or compatibility recipes beside
their replacements.

`out_dir` must be a dedicated child of the recipe root; use the inherited
convention `out_dir = "out"`. Do not point it at source, a parent/workspace
directory, or a repository directory. A `[clean]` target is only for
additional regeneratable state outside `out_dir` (for example Cargo's local
`target/`) and must name that state narrowly. Never add `[clean] command =
"rm -rf out"`: Pekit already owns and removes `out_dir`.

The normal catalogue cleanup is:

```sh
pekit workspace clean
```

With no catalogue clean targets this removes each included member's managed
`out_dir` and preserves the signed repository. Preview
the exact member/path plan with `pekit --dry-run workspace clean`. Workspace
exclusions still apply: clean an intentionally excluded local-only recipe, such
as `dev.peios.dwed`, explicitly when required.

When a recipe generates maintained package fragments or inventories, make the
generator deterministic and give its `gen` target a read-only
`verify_commands` drift check. Commit only the intended reviewable result, mark
it as generated, and run `pekit verify` before packaging. Never hand-edit one
half of a generated relationship or commit transient compiler output as though
it were maintained source.

## Identity and naming

Every concrete package name is globally qualified.

- Peios-owned software uses `dev.peios.<product>`.
- Third-party software uses the reverse-DNS identity of the authoritative
  upstream, for example `org.gnu.bash`, `com.amd.amd-ucode`, or
  `io.github.eudev-project.eudev`.
- Split packages retain the complete base identity:
  `org.gnu.glibc-devel`, not `glibc-devel`.
- A testing-only Peios product belongs below `dev.peios.testing.*`.

Use the upstream authority, not `org.peios`, for software Peios merely
packages. Package identity does not rename the program's executable, service,
registry paths, application ID, protocol, or other externally defined product
identity.

`provides` is an interoperability contract, not a search alias. Declare only a
real substitutable capability: an ABI/SONAME, `pkgconfig(...)`, a service role
such as `init`, or another interface for which consumers may accept multiple
implementations. Do not provide an unqualified package name or add a
`replaces` edge for an undeployed historical name. Dependencies on a concrete
package use its full reverse-DNS name. Dependencies on a virtual capability are
appropriate only when substitution is intentional and tested.

Use `format = "peipkg"`, the official HTTPS homepage, the narrowest correct
architecture, a concise description of at most 80 characters, a complete SPDX
licence expression, and an explicit licence class. Package metadata is a public
interface: do not use placeholder descriptions, guessed ownership, or a project
mirror as the homepage.

## Package role and ownership

Before writing files, establish what the product is, who owns each interface,
and what an installation is meant to enable. For first-party software, check
the public contract in `../learn/` and the source repository rather than
inferring the product from filenames. A recipe review must cover:

- executable, library, service, and command-line interfaces;
- registry schema, vendor defaults, mutable state, and upgrade ownership;
- runtime identities, privileges, capabilities, security descriptors, and
  PIP/signing tier;
- service dependencies and startup ordering;
- initramfs versus system-root placement; and
- which payloads can sensibly be installed or upgraded independently.

Installing a package must not silently grant authority or activate an unsafe
development configuration. Experimental software may be rough; it may not be
ambiguous about what it installs or what trust it receives. Security-sensitive
development packages such as DWE must override inherited publication targets
and remain excluded from workspace-wide public publication.

## Source and release tracking

### Reproducible source

Declare exactly one reproducible source (`source.git`, `source.url`, or
`source.pypi`) and, if useful, one `source.local` development override. Published
packages must never depend on `source.local`, a sibling checkout, the current
branch, an uncommitted tree, or a moving URL without a lock assertion.

For Git releases, enumerate immutable release tags with a strict `tag_regex`,
render the tag from `ref`, and let the lock pin the resolved commit. First-party
catalogue recipes usually delegate build and package ownership to the tagged
public source tree:

```toml
out_dir = "out"
delegate = true

[source.git]
url       = "https://github.com/peios/example.git"
ref       = "v{{version}}"
versions  = ">= 0.1.0"
tag_regex = '^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$'

[source.local]
path = "../../example"
```

The release tag must identify a clean, public, immutable source state. Local
source exists for pre-release work only. Signed Git-tag enforcement is
currently deferred; do not claim a tag is authenticated when Pekit has only
locked its commit.

For URL/PyPI sources, use the canonical upstream archive and enough metadata to
enumerate stable releases. The lock must bind the exact bytes. Do not scrape a
mirror merely because it is convenient when an authoritative upstream channel
exists.

### Versions are an unattended update policy

The normal version constraint is a documented **soft minimum**:

```toml
# Soft maintenance floor. Older locked releases remain reproducible; routine
# discovery follows every newer stable release and relies on the build gates.
versions = ">= 3.2.14"
```

It limits the routinely maintained catalogue; it is not an assertion that
older upstream versions are incompatible. Do not add an upper bound merely to
avoid testing a future release. The point of this catalogue is for
`lock --latest` to discover, authenticate, and pin a new release without a
maintainer editing the recipe. A new upstream release should require human
intervention only when provenance changes or a build/test/package contract
breaks.

Use an exact version only for a genuine compatibility anchor such as a kernel
bootstrap compiler, a normative fixed data standard, or a deliberately
versioned toolchain slot. Explain that reason in the recipe. Parallel version
slots get distinct qualified identities; consumers pin the required slot.
A ceiling is acceptable only for the same kind of deliberately frozen
compatibility lane, with the rolling lane packaged separately and a precise
lint allowance explaining the boundary.

Map odd upstream versions into Peios' normal order where useful. Dated releases
use `YYYY.MM.DD`, even when an upstream tag or URL filename is `YYYYMMDD`;
named regex captures map the discovered components, and source templates render
the upstream spelling.

Version discovery must exclude prereleases, release candidates, signatures,
checksums, and unrelated assets unless the recipe explicitly packages them.
Keep the regex strict enough that an upstream web-page change fails closed
rather than becoming a version.

### Locks

Commit `pekit.lock`. It is the accepted source assertion and the basis for
historical rebuilds.

- `pekit lock --latest` discovers the newest acceptable release and adds its
  exact source identity to the lock. It does not discard older entries.
- `--all-versions` means every upstream version admitted by the constraint and
  can be expensive. It is not the same as `package --all`, which selects all
  package splits for the selected version.
- Never hand-edit a digest or casually use `--repin`. Repinning says that
  different bytes are now accepted for the same version and requires an
  explicit provenance/security review.
- `--refresh-source` may refresh the cache, but the lock must still reject
  changed bytes or commits.
- Retain useful historical lock entries. Raise the soft floor to control
  routine maintenance rather than deleting provenance.

### Source authentication

Use upstream signatures whenever an authentic signature channel exists:

```toml
[source.url.signature]
url          = "{{source_url}}.sig"
of           = "artifact"
key_files    = ["keys/release-key.asc"]
fingerprints = ["FULL_PRIMARY_KEY_FINGERPRINT"]
```

Commit only the minimal public key material needed for verification, pin the
complete primary-key fingerprint, and document where that identity was
established. A key rotation is a trust decision, not an automatic recipe
update. Do not fetch keys from a keyserver during a build.

If upstream publishes no signature format Pekit can verify, add a narrow
`source.signature.required` allowance in the member's `lint.pekit.toml`. State
what upstream actually provides and where the immutable lock becomes the trust
boundary. An allowance records a real limitation; it must not pretend HTTPS or
a checksum is a maintainer signature.

`ignore_expiry = true` is an exceptional compatibility switch for a release
whose valid signature was made with the pinned upstream key but is rejected
only because that key is past its declared expiry. It permits upstream to keep
making signatures with that expired key; it does not disable fingerprint,
cryptographic-signature, present revocation, critical-notation, future-time,
explicit signature-lifetime, identity-certification, or subkey-binding checks.
Explain the specific upstream practice beside it. Never use it to paper over an
unknown key, invalid signature, revoked key, or unauthenticated release.

### Patches

Prefer a current upstream release over accumulating downstream backports. A
rolling source policy does not eliminate patches: carry one when Peios needs a
platform integration change, when the current release has a release-blocking
defect, or while an upstream fix has not reached a release.

Every local patch must be in `patches/series` and apply with a defined strip
level. Its header follows [DEP-3](https://dep-team.pages.debian.net/deps/dep3/)
(or is `git format-patch` output) and carries three things, which lint checks:

- **What and why:** `Description:` or `Subject:`, saying why Peios needs the
  patch and the postcondition it enforces.
- **Provenance:** `Origin:`, `Author:` or `From:`. A patch Peios wrote says
  exactly `Author: Peios maintainers <packaging@peios.org>`; an imported one
  keeps its upstream author. Tools that helped write a patch are not authors.
- **Upstream status:** `Forwarded:` (a URL, `no`, or `not-needed` for a
  Peios-only platform change), `Applied-Upstream:` (the release or commit that
  contains it), or `Origin: upstream, <commit>` / `Origin: backport, <url>`. This
  is what tells an upgrade which patches it can drop.

Prefer a patch that fails to apply after an
upstream change over a permissive `sed` that silently stops doing the intended
work. Drop backports as soon as the selected upstream release contains them.
Authenticate and lock an upstream remote patch series just like its base
archive.

## Hermetic build graph

Every build and test target declares its native (Peipkg) dependencies:

```toml
[build.main.dependencies.peipkg]
"org.git.kernel.dash" = "*"
"org.gnu.make" = "*"
```

Recipes tagged `minimal-bootstrap` also declare a Debian (apt) set for every
target, because they are built under `--env debian` to seed an empty
repository (see [Bootstrapping](#bootstrapping-from-an-empty-repository)):

```toml
[build.main.dependencies.apt]
dash = "*"
make = "*"
```

No other recipe declares apt sets or builds under Debian; asking one to fails
with `missing_dependency_provider`.

An empty provider table means “none” and is preferable to an implicit host
dependency. Name the Peios implementation actually used: for example Peios
base utilities are `dev.peios.peiosutils`, not an accidental dependency on GNU
coreutils. Declare tools invoked indirectly by configure, test harnesses,
scripts, code generators, and package post-processing. Do not depend on what
happens to be installed in the developer's host or composed root.

For a seed recipe, the Debian build must supply inputs equivalent to the
native one, and its staged result must pass the same tests; the seed is then
rebuilt natively. Some inputs Debian cannot supply, and
`_debroot_/reference.py` provides them without trusting anything outside the
Peios build's own roots:

- **Rust.** Seed recipes that need a newer compiler than Debian's (resolvd,
  peiosutils) receive Rust's own signed release archives, pinned by hash in
  `reference.py` and verified against the release key in `_debroot_/keys` on
  download (1.98.1; 1.83.0 with rust-src for the kernel's Rust targets).
  Debian's `cargo`, `rustc` and `rustfmt` are then dropped from the root.
  Native Rust bootstraps from the same upstream binaries.
- **Catalogue packages.** An apt set may name a reverse-DNS catalogue
  package, such as `"dev.peios.libpeios-devel" = "= 0.5.0-1"`. The preparer
  composes it from the signed repository, verified against
  `_peiroot_/repository.anchor`, and copies into the Debian root only the
  files the named packages own, never their Peios dependency closure.
  `dev.peios.kernel-headers` contributes only `usr/include/pkm`; Debian's
  `linux-libc-dev` keeps the Linux UAPI. Because the apt set names a package a
  member defines, workspace runs order that member first even under
  `--env debian`. Name every catalogue package the build uses, runtime library
  included.

Each root runs its toolchain and SDK through loader, compile and link checks
before any recipe command, and records what it installed in
`/usr/share/pekit-reference/reference-prerequisites.json`.

The Debian preparer accepts concrete APT package names (including an optional
architecture qualifier), `*`, or comma-separated comparisons using `=`, `>=`,
`>`, `<=` and `<`. Versions use Debian's epoch and tilde ordering. It filters
available candidates against every constraint, installs all direct dependencies
in one APT transaction, then verifies their final installed versions. Unsupported
syntax and unsatisfied requirements stop the job. Virtual package names must be
replaced with the concrete implementation the recipe needs.

Every fresh job pulls `debian:trixie` once and uses its immutable image ID for
all Debian roots in that job. Ordinary jobs keep following the current archive;
recipes do not need manually maintained exact version pins. Each prepared root
is automatically retained as a SHA-256-addressed archive under
`${XDG_STATE_HOME:-$HOME/.local/state}/pekit/debian-roots`, or the coordinator's
`PEKIT_DEBIAN_ROOT_STORE`. This store is separate from disposable job outputs
and has no automatic garbage collection. Back it up with release evidence;
source packages carry the small per-target records, not the root archives.

To replay a retained environment, set `PEKIT_DEBIAN_REPLAY` to its saved
`build-environment/` directory and `PEKIT_DEBIAN_ROOT_STORE` to the archive store
before running Pekit or the source bundle's `rebuild.py`. Replay verifies the
captured preparer identity, architecture, requests, package inventory and archive
hash; a missing or incompatible record fails without falling back to acquisition.
Replay uses Python 3.11+, GNU tar and the normal Pekit/Bubblewrap runtime, without
Docker or APT access. It freezes the dependency filesystem, not the host kernel,
CPU, build timestamps, signing keys or language-vendoring network policy. Retain
all referenced archives for as long as the corresponding release is supported.

Compilation and testing are offline. If an ecosystem requires vendoring, give
the hash-pinned materialization target an explicit `build:vendor` boundary; the
default environment grants network access to that target alone, and all
compiler and test targets stay offline. Never give the whole build network
access.

The acquisition root is composed from the vendor target's declared native
dependencies, which must not be empty. Peios glibc resolves hosts only through
resolvd's socket, which a build root does not run, so that root also receives
`dev.peios.resolvd-nss`
and `_peiroot_/buildroot-resolver.py`, which the profile's sandbox entry
(`_peiroot_/entry.sh`) starts for the job and which answers from the
`resolv.conf` Pekit copies in. TLS trust is rendered from
`org.mozilla.ca-certificates` at `/etc/ssl/certs/ca-certificates.crt` and
OpenSSL's default `/etc/ssl/cert.pem`. The root adds only that machinery and a
shell: declare every tool the vendor command runs, as in any native root.
Cargo fetches Git dependencies with its built-in client unless the recipe sets
`CARGO_NET_GIT_FETCH_WITH_CLI`, which needs `com.git-scm.git`. Go recipes
should set `GOTOOLCHAIN=local`, so a `go.mod` bump fails instead of
downloading another compiler.

A vendor target must declare a non-empty native set. Only a
`minimal-bootstrap` recipe's vendor target, run under `--env debian`, acquires
in a Debian root instead, from its apt set. Python test tools are fetched by pip running from its own
wheel, which `_pybuild_/test-tools` downloads by PyPI's published digest, so
acquisition needs only the root's Python.

If a delegated first-party recipe needs a remote upstream tree as a build
input, package that tree separately under the upstream's qualified identity.
The source recipe owns authenticated acquisition and a committed lock; the
delegated recipe consumes its installed, versioned payload offline through an
explicit Peipkg dependency. Pin the dependency exactly when local patches are
derived against one specific upstream release, and document that coordinated
rebase exception narrowly. Do not clone or download an undeclared tree from a
build command.

Use the inherited distribution flags. If an upstream build system ignores
them, pass them through correctly or rely on toolchain defaults and verify the
result. A justified package-specific exception belongs in the recipe and its
lint allowance, with the smallest possible scope.

Build scripts must be fail-fast (`set -eu` or stricter), quote paths, use stable
sorting (`LC_ALL=C`), and validate assumptions before transforming files.
Avoid timestamps, filesystem iteration order, absolute build paths, host CPU
detection, and unbounded parallelism as output inputs. Use source/lock
timestamps, deterministic archive modes, `gzip -n`, path remapping, and similar
upstream controls where applicable.

## Dependencies

Declare a dependency where the installed payload needs it, not merely where the
build happened to use it.

- Same-source split packages pin each other exactly with `"= {{release}}"`,
  which pekit renders as the package's own version-revision. This prevents
  mixing family revisions whose files and contracts were tested together, and
  cannot go stale when the revision is bumped. Lint rejects the hand-written
  `"{{version}}-N"` form.
- External concrete dependencies use qualified names and the narrowest honest
  compatibility floor. Avoid `*` when a known API/format minimum exists; avoid
  exact external versions unless compatibility truly requires one.
- Pekit derives ordinary ELF SONAME requirements/provides. Add explicit runtime
  dependencies for shell interpreters, helpers executed by name, `dlopen`
  plugins, data/schema consumers, services, and generated configuration because
  ELF scanning cannot see them.
- Apply dependencies to the root that consumes them. Initramfs packages and
  hooks must declare the initramfs root rather than pulling system-root state by
  accident.
- Portable scripts, metadata, and data use `noarch`, even when they depend on
  native packages. Resolve those dependencies for the target machine; a native
  dependency does not make portable payload architecture-specific. Machine code,
  architecture-specific firmware, and ABI-specific generated files still need
  the appropriate architecture. Document any architecture-constrained source or
  header split whose payload alone does not establish that constraint.
- Declare conflicts/replaces only for real co-installation or upgrade
  semantics, not as historical decoration.

After any rename or dependency correction, rebuild every affected package
revision. Editing a recipe does not alter manifests already published in a
repository. Resolve a fresh image/package closure and inspect it for the old
name; stale transitive artifacts are a release blocker.

## Package split and payload

Split on independent installation, use, security, and upgrade ownership—not on
the number of files. A mature library/application family commonly has:

- the principal runtime or library;
- separately useful command-line utilities or daemons;
- architecture-independent common data;
- `-devel` headers, unversioned link symlinks, pkg-config/CMake metadata, and
  development tools;
- `-static` archives when static linking is intentionally supported;
- `-doc` for substantial optional documentation;
- `-debuginfo` indexed by ELF build ID;
- `-debugsource` containing the exact sources referenced by rewritten DWARF;
  and
- a complete corresponding-source package when redistribution obligations or
  rebuildability call for it.

Produce `-debuginfo` and `-debugsource` with the shared helper rather than a
hand-written copy of the steps:

```sh
sh "$PEKIT_WORKSPACE_ROOT/_pkgtools_/split-debug" org.example.thing "$PEKIT_OUT/usr"
```

It rewrites DWARF paths to `/usr/src/debug/<package>`, requires a build ID and
debug info on every ELF, removes duplicate DWARF with `dwz` (per file, never
multifile), writes the build-ID-indexed debug files, strips executables,
shared objects and static archives appropriately, and copies exactly the
referenced sources. It fails rather than skipping anything; the one dwz
outcome it tolerates is an ELF over dwz's DIE limit, which keeps its DWARF
unoptimised. Debugedit and DWZ come from `dev.peios.build-essentials-c`; a
`minimal-bootstrap` recipe's Debian set names `debugedit` and `dwz` itself.
Compile with `-ffile-prefix-map`/`-fmacro-prefix-map` pointing the build root
at the same `/usr/src/debug/<package>` prefix. Toolchain recipes whose splits
need per-component debug trees (GCC, glibc, LLVM, Rust, Python, the kernel)
keep their own logic.

Do not create tiny arbitrary splits that can never be used independently, and
do not collapse optional development/static/debug payload into the runtime.
Dependency-only metapackages contain no fake marker files. Firmware blobs that
are themselves the upstream distributable may justify disabling a duplicate
source package; document why.

Every file must have one clear owner. Review the staged payload rather than
assuming `make install` did the right thing:

- remove libtool `.la` files and build-system debris unless they are a required
  public interface;
- place architecture libraries in `/usr/lib/<Peios triplet>`;
- put vendor configuration defaults under `/usr/etc`, registry seeds under
  `/usr/share/regim`, and mutable state under the appropriate `/var` location;
- do not write live host `/etc` during the build—Peios composes vendor and
  mutable configuration through its own strata;
- preserve required symlinks, but reject dangling or absolute payload symlinks;
- compress manual pages consistently and install licences under
  `/usr/share/licenses/<qualified-package>/`;
- ship man pages, never Info manuals: Peios has no Info reader or index. Where a
  Texinfo manual is a library's only complete reference (glibc, GMP, MPFR,
  MPC), build it as HTML with `texi2any --html` into that library's `-doc`
  package under `/usr/share/doc/<source family>/html/` (for example
  `/usr/share/doc/org.gnu.glibc/html/`);
- name every installed script's interpreter through the runtime view
  (`#!/bin/sh`, `#!/bin/bash`, `#!/bin/python3`, `#!/bin/perl`), never through
  `/usr` package storage or `/usr/bin/env`. The one exception is a boot hook
  that runs before the StrataFS views exist; it names `/usr/bin/sh`, says why,
  and carries a narrow lint allowance;
- exclude caches, test output, temporary files, empty accidental directories,
  duplicate ownership, and special files; and
- declare and test modes, ownership, xattrs, security descriptors, service
  registrations, and other metadata that ordinary file copying can lose.

For services, verify the configured image path exists in the composed image,
not just in the package archive. Registry/service seeds must agree with the
binary, dependencies, identities, startup model, and least-privilege design.
Packaging must never apply Peios security policy to the build host.

Licensing is part of the payload contract. Use a complete SPDX expression and
the correct `license_class`; use a documented `LicenseRef-*` only when no SPDX
identifier fits. Include all required licence/notices and corresponding source,
including downstream patches and build inputs. Do not call generated binaries
or caches “source”.

Rust links its crates statically, so a Rust package's licence covers every
crate it ships. Run `/usr/libexec/peios-packaging/collect-rust-licences`
(`dev.peios.packaging-tools`) after vendoring: it copies each crate's notices to
the package's `third-party/` licence directory and, with `--check`, fails unless
the package's declared `license` equals the combined expression of the shipped
crates.

Programs that use TLS declare no trust dependency. The machine's trust store is
provided by trustd and belongs to the image, not to each program; depending on
`org.mozilla.ca-certificates` gives a program nothing it can read.

### Target triplets

Ordinary autotools packages configure as `x86_64-pc-linux-gnu` (explicitly, or
through `config.guess`). That is the ABI they are built against: glibc and the
System V x86-64 ABI. Only components that bake the triplet into what they ship
use `x86_64-linux-peios`: GCC and binutils, through
`_pkgtools_/config-sub-peios.sh`. Python carries the Peios name through its
multiarch patch, not through configure.

## Validation gates

A successful compile is the start of review, not the end. Before publication,
the selected release must pass all applicable gates.

`pekit package` and `pekit publish` run two kinds of gate before anything is
published: every test target with `gate = true`, and lint — the recipe's static
rules, then the payload rules over the archives the run just wrote. `--no-gates`
skips both and is only for rapid local iteration. `--strict` is the publication
contract: it refuses uncommitted catalogue changes (other than `pekit.lock`),
unlocked or `--local` sources and every bypass flag, and on `publish` the
repository publisher additionally checks every active install closure and an
upgrade from every previously active one. Plain `publish` omits those closure
checks so a bootstrap can publish packages ahead of their dependencies.

### Build and upstream tests

Run the complete applicable upstream test suite against the just-built objects
from a `[test]` or named `[test.*]` target with `gate = true`. Keep build targets focused on
constructing and transforming their output. Immediate fail-fast preconditions
that make a transformation safe may remain beside that transformation, but
upstream suites, installed behavior, ABI/API checks, payload policy, hardening,
debug/source validation, and security regressions belong in gates.

Test targets declare their own native dependencies, and a `minimal-bootstrap`
recipe's test targets also declare an apt set; lint checks both. If a gate
uses a retained build tree, do not delete that tree in `build`; clean it after
the gate instead. When no runnable upstream suite exists (for example binary
firmware), provide rigorous gated structural/semantic validation of the staged
payload rather than a mere existence check.

### Installed-interface tests

Exercise the staged result as consumers will use it:

- `--version`/`--help` or an equivalent executable smoke test;
- compile and link against installed headers, shared libraries, static
  libraries, and pkg-config/CMake metadata as applicable;
- load plugins, locale/data files, registry schemas, and service definitions;
- check symlink targets, interpreter paths, shebangs, man pages, licences,
  permissions, and root placement; and
- test package-specific failure and integration paths, not only the happy path.

Tests must select the staged libraries and files explicitly rather than
silently using a copy already installed in the build root.

### Hardening and debug data

Verify the emitted ELF files, not just compiler flags. The workspace linter
expects PIE where applicable, non-executable stack, full RELRO/BIND_NOW, RELR,
CET, no RPATH/RUNPATH, no text relocations, build IDs, stripped runtime files,
separate debuginfo, and no leaked build paths. Exceptions for bootloaders,
loaders, kernels, static-only artifacts, or upstream constraints must be narrow,
technically justified, and tested.

CET notes alone are insufficient. `elf.cet` also inspects known indirect-call
entry points in the final payload, using matching build-ID debug symbols for
stripped files. Preserve compiler instrumentation and use `-z ibtplt` for PLT
entries; do not force IBT/SHSTK notes to conceal unmarked inputs. On a fully
marked native toolchain, `-z cet-report=error` checks the linked input notes.
Static inspection is bounded and does not replace runtime CET enforcement
checks or review of assembly and generated code. See the
[CET lint contract](https://learn.peios.org/pekit/running/linting).

Debug packages are functional deliverables. Confirm each shipped ELF build ID
resolves to its `.debug` file and that rewritten source paths resolve into the
debugsource payload. Strip debug sections from static archives unless the
package deliberately promises otherwise.

### Reproducibility

Build the same locked source twice in independent clean output paths and compare
the resulting package payloads and metadata. Investigate every difference.
Normal fixes include stable traversal/sorting, fixed timestamps, deterministic
archives, removed build IDs generated from non-deterministic input, remapped
debug paths, and excluding caches. Do not weaken the test merely because an
upstream build is awkward.

### Lint exceptions

Workspace lint is mandatory. Prefer path-scoped exceptions for intentional
payload files, so unrelated files remain checked:

```toml
[allow_files."payload.junk"]
"usr/lib/compiler/*/crtbegin.o" = "Required startup object linked into user programs"
```

Patterns refer to package destinations, not build-host paths. An exception
applies only to its named rule; unused exceptions remain visible in lint output.
Use a whole-rule exception only when the justification covers the whole recipe:

```toml
[allow]
"source.signature.required" = "Upstream publishes ...; the immutable lock is the available trust boundary"
```

The reason must be specific, current, and auditable. Never disable the root
rule, copy the whole root lint file, or use a generic “upstream does not support
it” waiver. A reviewer should be able to tell what evidence would allow the
exception to be removed later.

A limitation of a build environment rather than of any recipe belongs in that
environment's file as `[lint.allow]`, and applies only to what that
environment builds. `debian.env.pekit.toml` exempts `elf.cet` this way, because
Debian's startup objects carry no CET notes.

## Versions, revisions, and publication

The package version is the upstream version plus a Peios packaging revision,
normally `{{version}}-N`. Increase `N` whenever the same upstream source would
produce a materially different package, including changes to:

- patches, build flags, or build commands;
- payload, split, modes, xattrs, or metadata;
- dependencies, provides, conflicts, or roots;
- tests whose correction exposes a different accepted artifact; or
- signing/provenance policy represented by the package.

The revision is for recipe changes only. **A code change is a new version, not a
new revision.** For a first-party package, anything that changes what the source
builds (code, build system, tests, or the repo's own `pekit.toml` and package
definitions) is released from the first-party repository as a new version:
bump its version, tag `vX.Y.Z`, push, relock the member here, and start that
version at `-1`. Bump the revision only when this tree's recipe changes and
the same upstream source is rebuilt; a first-party fix never reaches a package
as a revision bump over an old tag. Every revision restarted at `-1` for the
September 2026 rebootstrap, so a revision above `-1` names a real recipe change
since then.

Do not overwrite or silently republish the same name/version/architecture with
different bytes. Rebuild every split in a source family at the new exact family
revision, even if only one member's dependency changed. Already published bad
artifacts remain historical; the repository's active index must prefer the
corrected revision.

Package signing and repository signing are distinct. Pekit signs each `.peipkg`
using `signing.package_key`; `publish.peipkg` signs repository metadata using
`signing.repository_key`. Recipe configuration refers to keyring leaves. Never
put a production private key or an absolute developer key path in a committed
recipe. Development keyrings are per-developer, gitignored qualification inputs
and must never be treated as public-repository custody.

`pekit publish` packages the selected package(s), runs the gates and publishes
them into `_repo2_`, creating the Peipkg repository if it does not exist.
Native builds install their dependencies from the same directory. `_repo2_`
replaced `_peipkgRepo_` for the September 2026 rebootstrap; the older
repository stays in place, frozen, only for images still composed from it.
Nothing publishes to it or installs from it for a build.
Repository publication currently regenerates the complete signed index from
repository contents; it is not an incremental database operation. The
repository is a directory of static files and requires no SQLite service.

Publish reviewed work with `--strict`, which also runs the publisher's install
and upgrade closure checks. Never use `--allow-unanchored` or `--allow-unsigned`
for production; `--strict` refuses both. Publish to a candidate/staging
directory when changing a production repository, run the full verifier (not
only `--quick`), and deploy the verified directory atomically. After every
publish:

```sh
peipkg-repo verify _repo2_
```

Verification includes the repository descriptor/index, package archives, and
signatures. Also resolve representative fresh package and image closures; repo
cryptographic validity alone cannot detect a semantically stale dependency.

## Standard workflow

Run commands from this directory. `PEKIT` below is illustrative; do not commit
machine-specific tool paths.

```sh
PEKIT=../pekit/out/pekit
RECIPE=org.example.product
```

1. Review the upstream release channel, signatures, version grammar, licences,
   distro packaging, public interfaces, installed payload, security model, and
   expected package split. Debian/Fedora are references, not specifications;
   retain their production lessons while adapting paths and integration to
   Peios.

2. Discover, authenticate, and append the newest lock:

   ```sh
   "$PEKIT" --recipe "$RECIPE" lock --latest
   git diff -- "$RECIPE/pekit.lock"
   ```

   If the recipe declares generated maintained files, also run its drift
   checks:

   ```sh
   "$PEKIT" --recipe "$RECIPE" verify --all
   ```

3. Build, test and package every split in the native environment. `package`
   runs the gated tests and lint over the finished archives:

   ```sh
   "$PEKIT" --recipe "$RECIPE" package --all --latest --keyring dev
   ```

4. Inspect the package manifests and payloads, repeat for reproducibility, and
   verify dependent/composed closures.

5. Review the entire diff, including locks, generated files, keys, patches, and
   package fragments. Confirm the source release is public and immutable, all
   revisions are fresh, the worktree contains no private/generated material,
   and no lint allowance is broader than necessary.

6. Commit the reviewed catalogue changes, then publish under the production
   contract:

   ```sh
   "$PEKIT" --recipe "$RECIPE" publish --all --latest --strict --keyring dev
   peipkg-repo verify _repo2_
   ```

For the whole catalogue, put workspace flags before the delegated command and
command flags after it:

```sh
"$PEKIT" workspace --jobs 4 lock --latest
"$PEKIT" workspace --jobs 4 --fail-fast package --all --latest --keyring dev
```

Choose concurrency according to memory and I/O cost. Toolchains and kernels can
exhaust the host when multiplied; unattended parallelism is not a quality gate.
Do not run workspace publication until every included recipe is intended for
that repository and all selected artifacts have passed the gates above.

Workspace runs order members by their gate and runtime dependencies, so a batch
publishes producers before consumers.

## Bootstrapping from an empty repository

The native environment installs everything from the catalogue itself, so an
empty repository needs a seed built elsewhere. Two recipe tags mark it:

- `minimal-bootstrap` (42 recipes) is the smallest set whose absence leaves no
  cycle among native build and test dependencies. It is the toolchain and
  ambient userland (`build-essentials-c` and what it installs, including DWZ for
  `split-debug`), plus the members
  that break the remaining cycles: bash, m4, tar, flex, gzip, ncurses, pkgconf,
  ca-certificates, e2fsprogs (Python links its libuuid) and resolvd (native
  acquisition needs its NSS module). bindgen joins them because the kernel's
  Debian build takes it from the catalogue, PCRE2 because the seed's grep links
  it, and Readline because the seed's gawk does.
- `bootstrap` (107 recipes, including those 42) is that seed closed under its
  own native dependencies: everything the seed needs to rebuild itself natively.
  Test dependencies count: the seed's gates need GDB (debugedit, dwz), DejaGnu
  with Expect and Tcl (binutils, gcc, dwz) and GoogleTest (ninja). Those are
  not seed members themselves; the Debian seed build takes Debian's `gdb`,
  `dwz` and `dejagnu` from its apt sets, and the native seed rebuild runs after
  they exist.

Only `minimal-bootstrap` recipes declare apt sets, so only they build in
Debian. The seed is then rebuilt natively, and everything else a second time
against the native seed. Those later rounds publish the same versions again,
which the repository normally refuses (a published version never changes), so
they pass `--replace` to overwrite the earlier builds:

```sh
"$PEKIT" workspace publish --all --latest --tag minimal-bootstrap --env debian
"$PEKIT" workspace publish --all --latest --exclude-tag minimal-bootstrap
"$PEKIT" workspace publish --all --latest --tag minimal-bootstrap --replace
"$PEKIT" workspace publish --all --latest --exclude-tag minimal-bootstrap --replace
```

`--replace` breaks the retention promise for the versions it overwrites. Use
it only on a repository nobody consumes yet, never on the public repository;
`--strict` refuses it.

A recipe joining `minimal-bootstrap` gains apt sets for every target; one
leaving it drops them. The sets are derived from declared dependencies
(PEI-1156). Recompute them when a recipe's native dependencies change which
members form cycles, and keep the tags in the member recipes, never in a
delegated source.

## Completion checklist

A package is ready for production publication only when all answers are yes:

- Is every package identity qualified and every `provides` entry a genuine
  substitutable capability?
- Will `lock --latest` find the next stable upstream release without editing
  the recipe, and is the floor soft rather than an arbitrary ceiling?
- Is source provenance authenticated as strongly as upstream allows and pinned
  in the committed lock?
- Are patches minimal, documented, fail-closed, and still necessary?
- Is every build/test input declared, with apt sets as well for a
  `minimal-bootstrap` recipe?
- Are compilation and testing offline except for an isolated, hash-pinned
  vendoring step?
- Does the split match real install/use/upgrade boundaries with exact internal
  edges and a complete runtime closure?
- Are licensing, corresponding source, configuration/state ownership,
  privileges, security metadata, and service integration correct?
- Do upstream, installed-interface, hardening, debug-data, and reproducibility
  tests pass in the native build environment?
- Does workspace lint pass, with only narrow evidence-based exceptions?
- Has every changed artifact received a new package revision, including all
  affected family/dependent packages?
- Are packages and repository metadata signed by the intended keys, fully
  verified, and validated in a fresh dependency/image closure?
- Is the repository clean of build output, private keys, stale aliases,
  temporary directories, and obsolete worktrees?

If any answer is unknown, the package is not yet production-grade. Investigate
or record a precise blocker; do not turn uncertainty into a broad exception.
