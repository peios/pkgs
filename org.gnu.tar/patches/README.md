# GNU tar 1.35 backports

This series is the narrow upstream/CentOS Stream delta needed while GNU tar
1.35 remains the latest signed stable release. It is not a forked downstream
feature set. Pekit's automatic release tracking deliberately stops if these
patches no longer apply, so a new stable release gets a one-time review and
the patches it contains can be removed.

The patch bytes come from the CentOS Stream 10 `tar` branch:

<https://gitlab.com/redhat/centos-stream/rpms/tar/-/tree/c10s>

- `0001` fixes atime restoration on read-only filesystems.
- `0002` is upstream commit `1e6ce98e3a4ef5c807458a35973af7e3503c678c`.
- `0003` restores two upstream test files omitted from the 1.35 tarball.
- `0004` is upstream commit `e290431ef27897afea228052425478f82d69fa29`.
- `0005` backports upstream extraction-jail and Gnulib `openat2` work for
  CVE-2025-45582.
- `0006` provides the interim `--one-top-level` diagnostic expected by the
  subsequent upstream fix.
- `0007` backports upstream commits `b009124f`, `b8d8a61b`, `67981bbb` and
  `19a3a73e` for CVE-2026-5704.
- `0008` backports the upstream absolute-`--one-top-level` series, including
  the CVE-2026-18508 fix. One context-only hunk was adjusted to apply to the
  pristine 1.35 release, which retains an extra wildcard guard at that site.
- `0009` backports upstream commits `0714d2f0`, `d479b2cc` and `b17665b2`
  for CVE-2026-18477.

Every added regression is regenerated and run by `make check` in both the
Debian reference environment and the native Peios package environment.
