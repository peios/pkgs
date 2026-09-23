# Release validation baseline — 2026-09-12

This is a diagnostic baseline from `pekit lint --latest --env peipkg-net --keyring dev`, not an acceptance report. It covers 120 public recipes. GCC and the kernel were deliberately excluded because their builds are unfinished; DWE is excluded from public workspace publication by policy.

The baseline found 16 passing recipes and 104 blocked checks: 38 missing stages, 6 missing payload selections, 36 payload-rule failures, 16 empty discoveries, 4 listing HTTP errors, 2 archive URL errors, and 2 untrusted signatures. A missing stage is not evidence that an earlier published artifact was defective. A payload finding may be a packaging defect or a linter false positive and must be triaged before changing policy. Newly discovered source versions still require their full release gates.

The full diagnostic log for this run is `/tmp/peios-payload-lint-20260912-gCFGWu.log`; that temporary file is not retained across shutdown. The per-recipe outcomes below are retained here while Acta is unavailable.

## Corrections after the baseline

- GCC: repaired configure-time CET interference with GNU symbol versioning; require exported GLIBCXX/CXXABI version definitions. The three-stage bootstrap and corrected release gates passed; the complete 16.2.0-1 family was packaged successfully at 17:24 on September 12. Payload lint and bootstrap publication remain separate checks.
- GCC tests: fix two invalid shell escapes, declare the freshly composed test root's compiler runtime/header dependencies, prefer the staged runtimes, and retain the build tree for a later gated publish without recompiling.
- GCC dependency: request the qualified Linux-header capability on its Linux version scale, rather than comparing a PKM package version to a Linux floor.
- Linter: source text under `usr/src/debug` is not automatically machine code; empty include directories do not require a development-package split. Regression tests and the full Pekit Go suite passed.
- Workspace lint policy: use the architecture-triplet library directory pattern so files in that directory are correctly identified as architecture-specific.
- Architecture decision (Jack, September 12): keep portable scripts and data `noarch`, including when they depend on native packages. Dependencies resolve for the target machine. Align the README and linter; do not waive actual ELF/triplet-content mismatches.
- GCC payload audit after the completed build: 31 findings, comprising 9 CRT startup objects classified as junk, 10 uncompressed manuals, 11 missing manual aliases/wrapper manuals, and the runtime `libcc1.so` plugin classified as a development link. The CRT objects and dlopen plugin are intentional payload and need narrow documented policy treatment; manual packaging needs correction. No ELF ABI/hardening/debug-symbol findings. Log: `/tmp/peios-gcc-payload-20260912.log`. Do not publish this family as release-accepted yet.

These fixes do not retroactively turn baseline failures into passes. Re-run affected checks after the changes and append their results.

### GCC lint closure — September 12, 17:42

- Corrected all 21 manual-page findings: deterministic gzip compression, command-name aliases, and an LTO-wrapper manual grounded in upstream `gcc/gcc-ar.cc` and `gcc/doc/invoke.texi`.
- Added gated gzip-integrity and manual-presence checks for every shipped public executable. Build and test roots explicitly depend on gzip.
- Added Pekit `allow_files` support with required reasons, relative destination globs, unused-entry reporting, and regression tests proving unrelated files still fail. GCC uses nine exact CRT basenames under its compiler directory and the single `usr/lib/x86_64-linux-peios/libcc1.so` runtime plugin path; no whole-rule waivers.
- Full Pekit Go tests and `go vet` passed. Recipe shell audit: 208 commands, no syntax failures.
- GCC 16.2.0 payload lint: **0 failures, 10 documented path-scoped exceptions**. Log: `/tmp/peios-gcc-lint-fixed-20260912.log`.
- Gated `package --all --version 16.2.0 --no-build --env peipkg-net --keyring dev` succeeded and regenerated the signed 16.2.0-1 family without recompiling. Log: `/tmp/peios-gcc-package-fixed-20260912.log`.
- Manual build-support files live under `packages.pekit/` so they are included in the corresponding-source archive; their archive presence was verified. Repository publication and the broader workspace acceptance pass remain outstanding.

### GCC bootstrap publication completed — September 12, 21:07

- Published the complete signed GCC **16.2.0-3** family (24 packages) to the
  existing private `_peipkgRepo_`. Gated `publish --all --version 16.2.0
  --no-build --env peipkg-net --keyring dev` succeeded; no compiler rebuild and
  no skipped gates. Log: `/tmp/peios-gcc-publish-20260912.log`.
- Revision 3 supersedes the private build repository's immutable revision 2.
  All temporary top-level version and same-family dependency edits have been
  **restored to `{{version}}-1`** for the clean public release set.
- Repository index advanced from 256 to **257**, with 945 active and 1,894
  archived entries. The archive retains all 24 older GCC entries plus the 24
  new entries. Non-GCC active entries are byte-equivalent after canonical JSON
  serialization. `peipkg-repo verify --quick` reports no problems; this verifies
  signatures/index consistency and presence/size, not a full historical rehash.
- A fresh disposable root selected the published GCC family and successfully
  compiled and ran a C++ program using strings, vectors and iostreams. Its
  libstdc++ exports GLIBCXX_3.4 and CXXABI_1.3, with IBT/SHSTK properties and no
  loader version warnings. Log: `/tmp/peios-gcc-published-smoke-20260912.log`.
  An initial temporary smoke script lacked its heredoc terminator and exited
  without running the compiler; that attempt was rejected, the script fixed,
  and the complete check rerun successfully. A separate direct compile/run also
  passed (`/tmp/peios-gcc-published-smoke-direct-20260912.log`).
- GCC's corrected runtime is now available to downstream builds. The broader
  workspace release-validation campaign and public deployment remain open.

### Native payload rerun batch — September 14, 01:05

- `org.oasis-open.docbook-xml`, `org.mozilla.ca-certificates`, `org.gnu.gzip`,
  `org.gnome.libxml2`, `org.gnu.libtool`, and `org.kernel.util-linux` were
  rebuilt from fresh managed outputs, passed their applicable upstream and
  installed-payload gates, produced signed revision-1 families, and now report
  zero payload-lint findings. DocBook XML retains three documented source
  policy allowances; libxml2 retains its documented missing-signature
  allowance; libtool retains seven documented upstream-layout/source-policy
  allowances.
- `io.github.rust-lang.bindgen 0.65.1-1` was rebuilt with runtime libclang
  closure, deterministic generated manual, split debug symbols and sources,
  remapped build paths, and linker-level IBT/SHSTK properties compatible with
  the kernel-pinned Rust 1.83 compiler. Its generation smoke test and hardening
  gates passed; payload lint reports zero findings and three documented source
  policy allowances.
- `io.github.thom311.libnl 3.12.0-1` passed its upstream suite, installed-tree
  C/C++ consumers, ABI, reproducibility, split-debug, and hardening gates. Its
  seven-package family was signed; payload lint reports zero findings and 42
  exact upstream-command manual-page allowances.
- `org.linux.traceevent 1.9.0-1` passed the maintained staged-library,
  ABI/plugin/documentation/reproducibility/hardening gates. The library and
  plugin debug symbols are independently installable and its man3 set is
  reproducibly compressed. Payload lint reports zero findings.
- `org.kernel.linux-firmware 2026.09.10-1` was authenticated against the
  pinned kernel.org signer, then its release-accounting gate identified the
  new TI TAS257x amplifier firmware. That driver was assigned to the existing
  `audio-codecs` family under the already-declared TI firmware licence. The
  rerun accounted for every WHENCE entry, validated every compressed blob and
  staged symlink, PIP-signed the firmware, and produced all 17 signed family
  packages. Payload lint reports zero findings and 18 path-scoped allowances
  for Broadcom board-data filenames whose spaces are part of exact kernel DMI
  lookup names.
- These results close this rerun batch only. They do not replace the remaining
  catalogue-wide fresh build/payload-lint pass or repository verification.

## Per-recipe baseline

| Recipe | Result | Diagnostic |
|---|---|---|
| `com.amd.amd-ucode` | pass | No payload findings |
| `com.darwinsys.file` | pass | No payload findings |
| `com.facebook.zstd` | blocked | version_selection_empty: no versions are available after source version filtering |
| `com.intel.intel-ucode` | blocked | lint_failed: 1 lint finding(s): package.architecture (1) |
| `com.mesonbuild.meson` | blocked | lint_failed: 17 lint finding(s): package.architecture (1), payload.manpages.compression (1), payload.scripts (4), split.devel.packages (11) |
| `com.xxhash.xxhash` | blocked | lint_failed: 4 lint finding(s): elf.debuginfo (1), package.architecture (2), payload.manpages.compression (1) |
| `cz.ucw.pciids` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/cz.ucw.pciids/out/git-tracked-fb0290ecf5ddfe4b/build/main; lint never builds — run `pekit build --version 2026.09.12` first |
| `cz.ucw.pciutils` | blocked | lint_failed: 8 lint finding(s): elf.debuginfo (1), package.architecture (2), payload.manpages.compression (5) |
| `dev.peios.atrium` | blocked | lint_failed: 6 lint finding(s): elf.cet (3), elf.debuginfo (1), package.architecture (1), payload.manpages.required (1) |
| `dev.peios.authd` | blocked | lint_failed: 6 lint finding(s): elf.cet (5), package.architecture (1) |
| `dev.peios.build-essentials` | blocked | lint_failed: 4 lint finding(s): package.architecture (4) |
| `dev.peios.coldplug` | blocked | lint_failed: 1 lint finding(s): package.architecture (1) |
| `dev.peios.disk-boot` | blocked | lint_failed: 2 lint finding(s): package.architecture (2) |
| `dev.peios.eventd` | blocked | lint_failed: 3 lint finding(s): package.architecture (1), payload.manpages.required (2) |
| `dev.peios.feat-dynamic-boot` | blocked | lint_failed: 1 lint finding(s): package.architecture (1) |
| `dev.peios.fsbase` | blocked | lint_failed: 5 lint finding(s): package.architecture (3), split.devel.packages (2) |
| `dev.peios.libpeios` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/dev.peios.libpeios/out/git-13bd41d5839f7d1b/build/main/usr/lib/x86_64-linux-peios/libpeios.so.0 has no matches |
| `dev.peios.librsi` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/dev.peios.librsi/out/git-7b10035b193a0a33/build/main/usr/lib/x86_64-linux-peios/librsi.so.0 has no matches |
| `dev.peios.live-boot` | blocked | lint_failed: 2 lint finding(s): package.architecture (2) |
| `dev.peios.loregd` | pass | No payload findings |
| `dev.peios.netd` | pass | No payload findings |
| `dev.peios.peinit` | pass | No payload findings |
| `dev.peios.peios-experimental` | pass | No payload findings |
| `dev.peios.peios-install` | blocked | lint_failed: 2 lint finding(s): package.architecture (1), payload.manpages.required (1) |
| `dev.peios.peios-installer` | pass | No payload findings |
| `dev.peios.peiosutils` | blocked | lint_failed: 122 lint finding(s): package.architecture (1), payload.manpages.compression (120), payload.manpages.required (1) |
| `dev.peios.peipkg` | pass | No payload findings |
| `dev.peios.pnpd` | pass | No payload findings |
| `dev.peios.prelude` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/dev.peios.prelude/out/git-1ebc3cb5c148dc4c/build/main/usr/bin/seed-sd has no matches |
| `dev.peios.resolvd` | blocked | lint_failed: 3 lint finding(s): package.architecture (1), payload.manpages.required (2) |
| `dev.peios.testing.peios-kernel-only` | pass | No payload findings |
| `dev.peios.timed` | pass | No payload findings |
| `dev.peios.trustd` | pass | No payload findings |
| `io.github.asciidoc-py.asciidoc` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/io.github.asciidoc-py.asciidoc/out/url-66e6eddf383423eb/build/main; lint never builds — run `pekit build --version 10.2.1` first |
| `io.github.besser82.libxcrypt` | blocked | version_selection_empty: no versions are available after source version filtering |
| `io.github.dosfstools.dosfstools` | blocked | version_selection_empty: no versions are available after source version filtering |
| `io.github.eudev-project.eudev` | blocked | lint_failed: 16 lint finding(s): elf.build_paths (6), elf.debuginfo (1), package.architecture (1), payload.license_file (3), payload.manpages.compression (5) |
| `io.github.hyperrealm.libconfig` | blocked | version_selection_empty: no versions are available after source version filtering |
| `io.github.numactl.numactl` | blocked | lint_failed: 14 lint finding(s): elf.build_paths (1), elf.debuginfo (1), package.architecture (2), payload.license_file (2), payload.manpages.compression (7), payload.manpages.required (1) |
| `io.github.rust-lang.bindgen` | blocked | url_versions: fetch URL listing https://static.crates.io/crates/bindgen-cli/: HTTP 403 Forbidden |
| `io.github.thom311.libnl` | blocked | version_selection_empty: no versions are available after source version filtering |
| `io.github.westes.flex` | blocked | lint_failed: 8 lint finding(s): elf.build_paths (1), elf.debuginfo (1), package.architecture (1), payload.license_file (3), payload.manpages.compression (1), payload.manpages.required (1) |
| `io.github.zlib-ng.zlib-ng` | blocked | lint_failed: 5 lint finding(s): elf.debuginfo (1), package.architecture (4) |
| `io.pagure.xmlto` | blocked | lint_failed: 4 lint finding(s): payload.license_file (2), payload.manpages.compression (2) |
| `io.pypa.flit-core` | blocked | lint_failed: 1 lint finding(s): package.architecture (1) |
| `io.pypa.setuptools` | blocked | lint_failed: 4 lint finding(s): package.architecture (1), payload.filenames (3) |
| `io.sourceforge.docutils.docutils` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/io.sourceforge.docutils.docutils/out/url-6f84cfc0ffc5201c/build/main; lint never builds — run `pekit build --version 0.23` first |
| `io.sourceforge.libisl.isl` | blocked | version_selection_empty: no versions are available after source version filtering |
| `net.sourceforge.e2fsprogs` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/net.sourceforge.e2fsprogs/out/url-a6f9efa0d9186b9a/build/main/usr/libexec/** has no matches |
| `net.sourceforge.perfmon2.libpfm` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.capstone-engine.capstone` | blocked | lint_failed: 8 lint finding(s): elf.build_paths (2), elf.debuginfo (1), package.architecture (2), payload.license_file (2), payload.manpages.required (1) |
| `org.cmake.cmake` | blocked | lint_failed: 45 lint finding(s): elf.build_paths (3), elf.cet (3), payload.filenames (24), payload.license_file (2), payload.manpages.required (3), payload.scripts (6), split.devel.packages (4) |
| `org.debian.netbase` | pass | No payload findings |
| `org.docbook.docbook-xsl` | pass | No payload findings |
| `org.figlet.figlet` | blocked | lint_failed: 6 lint finding(s): payload.license_file (2), payload.manpages.compression (4) |
| `org.git.kernel.dash` | blocked | lint_failed: 1 lint finding(s): payload.manpages.compression (1) |
| `org.gnome.libxml2` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.gnome.libxslt` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/org.gnome.libxslt/out/url-c09a979f44a59974/build/main/usr/lib/debug/** has no matches |
| `org.gnu.autoconf` | blocked | lint_failed: 7 lint finding(s): payload.manpages.compression (7) |
| `org.gnu.automake` | blocked | signature_invalid: signature https://ftp.gnu.org/gnu/automake/automake-1.19.tar.xz.sig does not verify against the pinned keys: openpgp: signature made by unknown entity — possible tamper or upstream key rotation; do not build until resolved |
| `org.gnu.bash` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.bash/out/url-758f49eb22793a5e/build/main; lint never builds — run `pekit build --version 5.3.15` first |
| `org.gnu.bc` | blocked | lint_failed: 7 lint finding(s): elf.build_paths (2), elf.debuginfo (1), elf.stripped (2), payload.manpages.compression (2) |
| `org.gnu.binutils` | blocked | lint_failed: 59 lint finding(s): elf.build_paths (21), elf.debuginfo (1), package.architecture (1), payload.license_file (4), payload.manpages.compression (18), payload.manpages.required (13), split.devel.packages (1) |
| `org.gnu.bison` | blocked | lint_failed: 8 lint finding(s): elf.build_paths (1), package.architecture (1), payload.license_file (3), payload.manpages.compression (2), split.devel.packages (1) |
| `org.gnu.coreutils` | blocked | missing_payload: file source /home/jack/projects/peios/pkgs/org.gnu.coreutils/out/url-6f673106ae31fb3a/build/main/usr/bin/** has no matches |
| `org.gnu.cpio` | blocked | lint_failed: 5 lint finding(s): elf.build_paths (1), elf.cet (1), payload.license_file (2), payload.manpages.compression (1) |
| `org.gnu.diffutils` | blocked | lint_failed: 6 lint finding(s): payload.license_file (2), payload.manpages.compression (4) |
| `org.gnu.findutils` | blocked | lint_failed: 6 lint finding(s): elf.build_paths (2), payload.license_file (2), payload.manpages.compression (2) |
| `org.gnu.gawk` | blocked | lint_failed: 30 lint finding(s): elf.build_paths (9), package.architecture (1), payload.license_file (3), payload.manpages.compression (15), payload.manpages.required (2) |
| `org.gnu.gettext` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.gettext/out/url-99a2b1a8f95470cc/build/main; lint never builds — run `pekit build --version 1.0` first |
| `org.gnu.glibc` | blocked | stage_missing: build target "locale" has no stage at /home/jack/projects/peios/pkgs/org.gnu.glibc/out/url-b36f3dae5d45fe64/build/locale; lint never builds — run `pekit build --version 2.44` first |
| `org.gnu.gmp` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.gnu.gperf` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.gperf/out/url-2b8bdfc7a38335ed/build/main; lint never builds — run `pekit build --version 3.3` first |
| `org.gnu.grep` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.grep/out/url-40895859d91e7124/build/main; lint never builds — run `pekit build --version 3.12` first |
| `org.gnu.gzip` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.gzip/out/url-5ce438aab6723687/build/main; lint never builds — run `pekit build --version 1.14` first |
| `org.gnu.libtool` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.gnu.m4` | blocked | download: https://ftp.gnu.org/gnu/m4/m4-4-1.4.21.tar.xz.tar.xz: HTTP 404 Not Found |
| `org.gnu.make` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.make/out/url-91ebc90a7f0f6fcc/build/main; lint never builds — run `pekit build --version 4.4.1` first |
| `org.gnu.mpc` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.mpc/out/url-019d6a5c834ab726/build/main; lint never builds — run `pekit build --version 1.4.1` first |
| `org.gnu.mpfr` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.mpfr/out/url-c87de2064a317ba9/build/main; lint never builds — run `pekit build --version 4.2.2` first |
| `org.gnu.ncurses` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.ncurses/out/url-1e29ad94f66966d1/build/main; lint never builds — run `pekit build --version 6.6` first |
| `org.gnu.patch` | pass | No payload findings |
| `org.gnu.sed` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.sed/out/url-fb9743ce9764479f/build/main; lint never builds — run `pekit build --version 4.10` first |
| `org.gnu.tar` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.tar/out/url-d22520bc88d77247/build/main; lint never builds — run `pekit build --version 1.35` first |
| `org.gnu.texinfo` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.texinfo/out/url-70e3e48e5c94f62d/build/main; lint never builds — run `pekit build --version 7.3` first |
| `org.gnu.which` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.gnu.which/out/url-086e7ab5f6fe78bc/build/main; lint never builds — run `pekit build --version 2.25` first |
| `org.golang.go-stage0-1.24` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.golang.go-stage0-1.24/out/url-c481fafe863c062d/build/main; lint never builds — run `pekit build --version 1.24.6` first |
| `org.golang.go` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.golang.go/out/url-15b186a6475ad3ea/build/main; lint never builds — run `pekit build --version 1.27.1` first |
| `org.iana.tzdata` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.iana.tzdata/out/url-5220e1b4e7caa367/build/main; lint never builds — run `pekit build --version 2026d` first |
| `org.jedsoft.slang` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.kernel.kmod` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.kernel.kmod/out/url-2cadc2f0654ece80/build/main; lint never builds — run `pekit build --version 34.2` first |
| `org.kernel.libcap` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.kernel.linux-firmware` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.kernel.linux-firmware/out/url-4c0c8966251940c4/build/main; lint never builds — run `pekit build --version 2026.09.10` first |
| `org.kernel.linux-source` | pass | No payload findings |
| `org.kernel.pahole` | blocked | lint_failed: 19 lint finding(s): elf.build_paths (5), elf.debuginfo (1), package.architecture (1), payload.manpages.compression (1), payload.manpages.required (11) |
| `org.kernel.util-linux` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.kernel.util-linux/out/url-8bfe36ba9e786e4c/build/main; lint never builds — run `pekit build --version 2.42.3` first |
| `org.libc.musl-sysroot` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.libc.musl-sysroot/out/url-6b21c30c7904235d/build/main; lint never builds — run `pekit build --version 1.2.6` first |
| `org.linux.traceevent` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.linux.traceevent/out/git-eaf50370e3a77486/build/main; lint never builds — run `pekit build --version 1.9.0` first |
| `org.linux.tracefs` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.linux.tracefs/out/git-51128bc3298eabda/build/main; lint never builds — run `pekit build --version 1.8.3` first |
| `org.llvm.llvm-current` | blocked | signature_invalid: signature https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.1/llvm-project-23.1.1.src.tar.xz.sig does not verify against the pinned keys: openpgp: signature made by unknown entity — possible tamper or upstream key rotation; do not build until resolved |
| `org.llvm.llvm` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.mozilla.ca-certificates` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.mozilla.ca-certificates/out/git-tracked-32249c7dff835945/build/main; lint never builds — run `pekit build --version 2026.09.06` first |
| `org.mozilla.cbindgen` | blocked | url_versions: fetch URL listing https://static.crates.io/crates/cbindgen/: HTTP 403 Forbidden |
| `org.ninja-build.ninja` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.ninja-build.ninja/out/git-b7684956b96ec175/build/main; lint never builds — run `pekit build --version 1.13.2` first |
| `org.nixos.patchelf` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.nixos.patchelf/out/url-9c552a01989297d1/build/main; lint never builds — run `pekit build --version 0.19.1` first |
| `org.oasis-open.docbook-xml` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.openssl.openssl` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.openssl.openssl/out/url-a4d5ad74bc76e466/build/main; lint never builds — run `pekit build --version 4.0.2` first |
| `org.perl.perl` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.perl.perl/out/url-4b58e30d6be514e9/build/main; lint never builds — run `pekit build --version 5.44.0` first |
| `org.pkgconf.pkgconf` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.python.python3` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.python.python3/out/url-883189930aeda9c7/build/main; lint never builds — run `pekit build --version 3.14.7` first |
| `org.rust-lang.rust-1.83` | blocked | url_versions: fetch URL listing https://static.rust-lang.org/dist/: HTTP 416 Requested Range Not Satisfiable |
| `org.rust-lang.rust-stage0-1.82` | blocked | url_versions: fetch URL listing https://static.rust-lang.org/dist/: HTTP 416 Requested Range Not Satisfiable |
| `org.rust-lang.rust-stage0` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.rust-lang.rust-stage0/out/url-7771b815cd79c230/build/main; lint never builds — run `pekit build --version 1.98.1` first |
| `org.rust-lang.rust` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.rust-lang.rust/out/url-f22cd67d68b70387/build/main; lint never builds — run `pekit build --version 1.98.1` first |
| `org.samba.rsync` | blocked | version_selection_empty: no versions are available after source version filtering |
| `org.sofproject.sof-firmware` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.sofproject.sof-firmware/out/url-51de7e51a70f4357/build/main; lint never builds — run `pekit build --version 2025.12.2` first |
| `org.sourceware.bzip2` | blocked | download: https://sourceware.org/pub/bzip2/bzip2-2-1.0.8.tar.gz.tar.gz: HTTP 404 Not Found |
| `org.sourceware.debugedit` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.sourceware.debugedit/out/url-6d5f35965f1c2f54/build/main; lint never builds — run `pekit build --version 5.3` first |
| `org.sourceware.elfutils` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.sourceware.elfutils/out/url-908171bb3b607c8c/build/main; lint never builds — run `pekit build --version 0.196` first |
| `org.tukaani.xz` | blocked | stage_missing: build target "main" has no stage at /home/jack/projects/peios/pkgs/org.tukaani.xz/out/url-57bfd9ebd50139ba/build/main; lint never builds — run `pekit build --version 5.8.4` first |
