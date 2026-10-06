# Less 710 source verification

On 2026-09-27 GPG verified less-710.tar.gz with upstream's less-710.sig and
pubkey.asc, both linked from https://www.greenwoodsoftware.com/less/download.html.
Signer: Mark Nudelman, AE27252BD6846E7D6EAE1DD6F153A7C833235259.
The detached signature is retained here and the key under keys/.
Archive SHA-256: d1008fb78dcae1323ddab664bcb352a61f022b1b131bd8018548e021d975ec7a.

Pekit's OpenPGP library rejects DSA by default. The signature uses DSA/SHA-1;
this is a legacy-algorithm limitation, not a failed GPG verification. Jack
explicitly approved this less-only exception in PEI-1179. Pekit itself is not
weakened. The recipe's per-version SHA-256 table rejects unreviewed future
releases. Prefer upstream's modern signature if one becomes available.

Recheck in a disposable GNUPGHOME: import keys/mark-nudelman.asc, then run
`gpg --verify provenance/less-710.sig less-710.tar.gz` and compare the archive
with the SHA-256 above.
