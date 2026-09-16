# Peios package catalogue

This repository is the source of the packages published by Peios. A recipe is
production-grade only when it can follow upstream releases unattended, build
from declared inputs in clean environments, produce a deliberate package
split, pass tests against its installed payload, and publish signed artifacts
without relying on state from a developer's checkout.

This document is the packaging policy and review checklist. The root
[`lint.pekit.toml`](lint.pekit.toml) enforces the mechanical parts. A local
`lint.pekit.toml` may explain a genuine exception, but it does not lower the
quality bar. [`PACKAGE_PRODUCTION.md`](PACKAGE_PRODUCTION.md) is the historical
production-pass ledger, not the policy source.

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
- [`package.pekit.toml`](package.pekit.toml) supplies the local artifact pool
  and signed Peipkg repository targets.
- `debian.env.pekit.toml`, `peipkg.env.pekit.toml`, and
  [`peipkg-net.env.pekit.toml`](peipkg-net.env.pekit.toml) supply the clean
  Debian, native Peipkg, and networked source-vendoring environments.
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
directory, or `_peipkgRepo_`. A `[clean]` target is only for
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

Every local patch must be in `patches/series`, apply with a defined strip level,
and begin with at least `Description:` and `Author:` headers. Its description
must state why Peios needs it, its provenance or upstream status, and the
postcondition being enforced. Prefer a patch that fails to apply after an
upstream change over a permissive `sed` that silently stops doing the intended
work. Drop backports as soon as the selected upstream release contains them.
Authenticate and lock an upstream remote patch series just like its base
archive.

## Hermetic build graph

Every build and test target declares dependencies for both supported providers:

```toml
[build.main.dependencies.peipkg]
"org.git.kernel.dash" = "*"
"org.gnu.make" = "*"

[build.main.dependencies.apt]
dash = "*"
make = "*"
```

An empty provider table means “none” and is preferable to an implicit host
dependency. Name the Peios implementation actually used: for example Peios
base utilities are `dev.peios.peiosutils`, not an accidental dependency on GNU
coreutils. Declare tools invoked indirectly by configure, test harnesses,
scripts, code generators, and package post-processing. Do not depend on what
happens to be installed in the developer's host or composed root.

The Debian rung is an independent reference build. The Peipkg rung proves the
package can build using the distribution it helps create. Both must remain
usable. Provider names may differ, but they must supply equivalent inputs and
the staged result must satisfy the same tests.

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
the hash-pinned materialization target an explicit `build:vendor`-style boundary
and use `--env peipkg-net`; all compiler and test targets continue through the
ordinary offline `peipkg` environment. Never give the whole build network
access.

`peipkg-net` picks the acquisition root from the recipe's declared vendor
dependencies. A vendor target whose native set declares `org.golang.go`
acquires in the native Peipkg root. Go resolves hosts with its own resolver,
and the root gets `/etc/ssl/certs/ca-certificates.crt` from the declared
`org.mozilla.ca-certificates` bundle. Such recipes should set
`GOTOOLCHAIN=local`, so a `go.mod` bump fails instead of downloading another
compiler. Every other vendor target, including all Cargo and pip acquisition,
uses a clean Debian root built from its declared apt set. Peios glibc resolves
hosts only through resolvd, which a build root does not run. Declare both sets
either way. The Debian reference environment builds from the apt set, so
native acquisition does not replace it.

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

- Same-source split packages use an exact package version such as
  `"{{version}}-4"`. This prevents mixing family revisions whose files and
  contracts were tested together.
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

## Validation gates

A successful compile is the start of review, not the end. Before publication,
the selected release must pass all applicable gates in both clean environments.

### Build and upstream tests

Run the complete applicable upstream test suite against the just-built objects
from a `[test]` or named `[test.*]` target with `gate = true`. Package and
publish run gates by default; `--no-gates` is only for rapid local iteration and
must never be used for release qualification. Keep build targets focused on
constructing and transforming their output. Immediate fail-fast preconditions
that make a transformation safe may remain beside that transformation, but
upstream suites, installed behavior, ABI/API checks, payload policy, hardening,
debug/source validation, and security regressions belong in gates.

Test targets must declare their own dependencies for both providers. If a gate
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

## Versions, revisions, and publication

The package version is the upstream version plus a Peios packaging revision,
normally `{{version}}-N`. Increase `N` whenever the same upstream source would
produce a materially different package, including changes to:

- patches, build flags, or build commands;
- payload, split, modes, xattrs, or metadata;
- dependencies, provides, conflicts, or roots;
- tests whose correction exposes a different accepted artifact; or
- signing/provenance policy represented by the package.

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

`pekit publish` packages the selected package(s) and publishes them directly
into the development/bootstrap `_peipkgRepo_`. This repository is not the public
release target. It creates the Peipkg repository if it
does not exist. Repository publication currently regenerates the complete
signed index from repository contents; it is not an incremental database
operation. The repository is a directory of static files and requires no
SQLite service.

Never use `--allow-unanchored` or `--allow-unsigned` for production. Publish to
a candidate/staging directory when changing a production repository, run the
full verifier (not only `--quick`), and deploy the verified directory
atomically. After every publish:

```sh
peipkg-repo verify _peipkgRepo_
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

3. Build/test/lint in the clean Debian reference environment:

   ```sh
   "$PEKIT" --recipe "$RECIPE" test --latest --env debian
   "$PEKIT" --recipe "$RECIPE" lint --latest --env debian
   ```

4. Repeat in the native offline Peipkg environment. Use `peipkg-net` only for a
   deliberately isolated vendoring target:

   ```sh
   "$PEKIT" --recipe "$RECIPE" test --latest --env peipkg --keyring dev
   "$PEKIT" --recipe "$RECIPE" lint --latest --env peipkg --keyring dev
   ```

5. Build every split, inspect the package manifests/payloads, repeat for
   reproducibility, and verify dependent/composed closures:

   ```sh
   "$PEKIT" --recipe "$RECIPE" package --all --latest --env peipkg --keyring dev
   ```

6. Review the entire diff, including locks, generated files, keys, patches, and
   package fragments. Confirm the source release is public and immutable, all
   revisions are fresh, the worktree contains no private/generated material,
   and no lint allowance is broader than necessary.

7. Commit reviewed catalogue changes, then let the release coordinator discover,
   build, qualify and promote the next candidate with the intended signing keyring:

   ```sh
   "$PEKIT" --recipe "$RECIPE" release --all --latest --keyring production
   peipkg-repo verify _publicRepository_
   ```

For a whole-catalogue qualification, put workspace flags before the delegated
command and command flags after it:

```sh
"$PEKIT" workspace --jobs 4 lock --latest
"$PEKIT" workspace --jobs 4 --fail-fast lint --latest --env peipkg --keyring dev
"$PEKIT" workspace --jobs 4 --fail-fast package --all --latest --env peipkg --keyring dev
```

Choose concurrency according to memory and I/O cost. Toolchains and kernels can
exhaust the host when multiplied; unattended parallelism is not a quality gate.
Do not run workspace publication until every included recipe is intended for
that repository and all selected artifacts have passed the gates above.

## Completion checklist

A package is ready for production publication only when all answers are yes:

- Is every package identity qualified and every `provides` entry a genuine
  substitutable capability?
- Will `lock --latest` find the next stable upstream release without editing
  the recipe, and is the floor soft rather than an arbitrary ceiling?
- Is source provenance authenticated as strongly as upstream allows and pinned
  in the committed lock?
- Are patches minimal, documented, fail-closed, and still necessary?
- Are every build/test input and both dependency-provider mappings declared?
- Are compilation and testing offline except for an isolated, hash-pinned
  vendoring step?
- Does the split match real install/use/upgrade boundaries with exact internal
  edges and a complete runtime closure?
- Are licensing, corresponding source, configuration/state ownership,
  privileges, security metadata, and service integration correct?
- Do upstream, installed-interface, hardening, debug-data, and reproducibility
  tests pass in both clean build rungs?
- Does workspace lint pass, with only narrow evidence-based exceptions?
- Has every changed artifact received a new package revision, including all
  affected family/dependent packages?
- Are packages and repository metadata signed by the intended keys, fully
  verified, and validated in a fresh dependency/image closure?
- Is the repository clean of build output, private keys, stale aliases,
  temporary directories, and obsolete worktrees?

If any answer is unknown, the package is not yet production-grade. Investigate
or record a precise blocker; do not turn uncertainty into a broad exception.


## Qualified production releases

`pekit release --all --latest --keyring production` selects upstream once per
recipe. `pekit workspace --jobs 4 release --all --latest --keyring production`
qualifies all selected members before promoting a single repository batch.
No per-release recipe pin or additional human approval is required for a normal
successful run. Version discovery happens again on the next attempt.

Production requires a clean committed catalogue. Release builds use distinct
fresh paths in both configured environments and copies of one frozen source
snapshot. Generated-file checks, declared release tests, configured recipe lint,
and payload lint of the signed final archives must pass. Source/helper inputs,
actual dependency identities, logs, exemptions, archive hashes and tool identity
are retained under `.pekit/releases/candidate-*`. Keep this store and retained
build-root archives backed up for the supported lifetime.

The native artifacts are copied into a candidate repository. The publisher
checks every active install closure and upgrades from every previous active
closure, including root placement, missing capabilities, conflicts and payload
collisions. Candidate files have independent inodes; checks cannot accidentally
write through a hard link to a live archive. Required release checks then run
against `PEKIT_RELEASE_REPOSITORY`, with selection details in
`$PEKIT_RELEASE_DIR/candidate.json`. Missing or failing checks, modified inputs,
evidence or archives, or a changed base repository reject promotion.

`_release_/commands.toml` is the committed, version-independent command map for
source reconstruction, independent reproducibility, and product integration.
Its entries are intentionally unconfigured while audit items 8–10 are unfinished.
`_release_/check.py` fails for missing entries; it never substitutes an existing
ledger, a success flag, or a skipped check. Wire real test commands there as those
items are completed. The dispatcher and coordinator retain their output and exit
status automatically. These are trusted maintainer orchestration commands;
never route downloaded upstream scripts into this coordinator interface. Build
and package tests continue to use isolated workers.

Only after all checks pass does Pekit sign `release.json` and promote its exact
archive set into `_publicRepository_`. Protected repositories use publisher
state schema 2, which older tools reject; ordinary `publish`, unsigned evidence,
missing logs and changed artifacts cannot satisfy this boundary. Public repository
wire formats are unchanged. The signed receipt records the tested candidate;
`PROMOTED.json` records the actual resulting index. A process or disk failure
during index writes can still need the normal repository verification/recovery
procedure. A batch is not a claim of an atomic multi-file filesystem transaction.

Do not deploy the bootstrap repository wholesale or point the release target at
it. Failed candidates remain available with diagnostics and cannot be resumed
by trusting a saved success bit: rerun qualification. This infrastructure does
not establish full catalogue readiness, bit-for-bit reproducibility, guest boot,
or supported upgrade behavior until their required checks actually run.


Automatically managed `pekit.lock` updates are exempt from the clean-catalogue
check and are captured as exact candidate inputs. A successful upstream release
therefore does not force a human to commit its generated lock before the next
attempt. Recipe, helper, lint, environment and release-policy changes still
require a reviewed commit; lock integrity/source-authenticity checks still apply.
