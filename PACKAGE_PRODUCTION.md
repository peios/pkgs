# Package production campaign

> Temporary task ledger while Acta is unavailable. Move durable work history
> back to the relevant Acta items when service is restored; do not create
> duplicate tasks in the meantime.

## Objective

Work through the 113 recipes in this repository, in alphabetical order,
bringing each to production standard, validating it on the Debian reference
rung and the native Peios rung, and publishing signed packages to the local
`peios` peipkg repository. First-party Peios recipes are deferred for a later
pass. If a package needs a product or architecture decision, record the
question here, skip it, and continue with the next independent package.

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

- Last completed recipe: `org.gnu.tar` at pkgs commit `45a3cab`.
- Completed: **74 / 113** recipes (65.5%).
- Current upstream/dependency pass: **74 / 85** recipes (87.1%).
- Deferred first-party pass: 28 recipes.
- Repository after GNU tar publication: index version 155, 456 active entries,
  689 archived entries, no verification problems.
- Signing fingerprint:
  `63977c7be45624999b88bac5aa55ab5280656ee076617a285c87602a0d980602`.

The 74 completed recipes are the currently tracked reverse-DNS recipe
directories. The remaining recipes in the current pass are listed below.

## Remaining current-pass recipes

| Order | Recipe | State | Notes |
| ---: | --- | --- | --- |
| 1 | `ca-certificates` | Decision deferred | See the trust-source decision below. |
| 2 | `dash` | Tooling deferred | Upstream's current four-part version needs ordered Pekit representation; see below. |
| 3 | `debugedit` | Next | GDB/DWZ coverage remains a separate follow-up. |
| 4 | `docbook-xsl` | Pending | |
| 5 | `gcc` | Pending | Large native bootstrap; preserve its deliberate Peios-specific toolchain policy. |
| 6 | `glibc` | Pending | Large native bootstrap and ABI-critical validation. |
| 7 | `libtraceevent` | Pending | Rename/package-family production work was previously tracked separately. |
| 8 | `libtracefs` | Pending | Depends on the libtraceevent migration. |
| 9 | `libxml2` | Pending | |
| 10 | `libxslt` | Pending | |
| 11 | `mpc` | In progress elsewhere | Do not touch the existing uncommitted `mpc` to `org.gnu.mpc` migration. |

## Deferred first-party recipes

`atrium`, `authd`, `build-essentials`, `coldplug`, `disk-boot`, `eventd`,
`feat-dynamic-boot`, `fsbase`, `kernel`, `libpeios`, `live-boot`, `loregd`,
`mockinit`, `netd`, `peinit`, `peios-dwe`, `peios-experimental`,
`peios-install`, `peios-kernel-only`, `peiosutils`, `peipkg`, `pnpd`,
`prelude`, `resolvd`, `timed`, and `trustd`, plus the already-qualified
`dev.peios.oobe` and `dev.peios.peios-installer` recipes.

## Follow-ups and known blockers

- Package GNU Readline separately and then enable it in Bash and `bc`.
  This was previously Acta item PEI-613 (`7qq9qu2h`).
- Allow recipes to declare precise source-package license metadata; until
  then, generated source packages necessarily share family metadata.
- Fix `verify.sh` file/directory prefix ordering drift where the shell checker
  disagrees with canonical `archive.VerifyFormat`.
- Package GDB and DWZ to close Debugedit's complete upstream-test coverage.
- Extend Pekit's selected-version model or Git-tag mapping so upstream
  four-component releases retain their spelling and ordering. Dash is now at
  `v0.5.13.5`, while Pekit accepts at most `MAJOR.MINOR.PATCH`; mapping the
  fourth component to build metadata would make it order-insignificant and
  mapping it to a prerelease would be semantically wrong and eventually sort
  `10` before `9`. The audited Dash production draft is preserved in the
  isolated `codex/org-git-kernel-dash-production` worktree and should use the
  official kernel.org Git tags once this representation is resolved.
- Resolve the long-term coexistence boundary between `peiosutils` and the
  POSIX/GNU-compatible tools needed by native package builds.
- Keep migration dependencies compose-safe while qualified and legacy package
  names coexist.

### `ca-certificates`: trust-source and cadence decision

The existing recipe deliberately consumes `certdata.txt` from Firefox's moving
release branch because that is Mozilla's authoritative root-store source and
receives additions/removals before the next NSS release. That URL has no
enumerable version, however, so the dated version and lock must be updated by
hand. It also downloads curl's live bundle during the build, which is useful as
an independent conversion check but makes the build non-hermetic.

The official Mozilla NSS repository has mechanically enumerable
`NSS_3_<minor>_RTM` tags (3.128 is current at this checkpoint), allowing Pekit
to discover and pin releases automatically. The trade-off is a different
security policy: root-store changes wait for the monthly NSS release cadence,
and the Git tags are lightweight rather than cryptographically signed. The
Mozilla release archives provide SHA-256 files on the same origin, not an
independent signature. Curl's dated CA Extract archive is another enumerable
cross-check, but making it the primary source would delegate conversion to a
third party.

Choose whether Peios prioritises the freshest Firefox release-branch trust
store with a small automated snapshot/versioning extension, or accepts NSS
release cadence so the existing generic Git-tag tracker can be used. Until
then, preserve the current trust input and do not publish a semantic change.

## Latest completion: GNU tar 1.35-2

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
