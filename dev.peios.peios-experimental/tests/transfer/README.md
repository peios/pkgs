# Native rsync and OpenSSL checks

`run.py` boots a disposable Peios VM with the packaged binaries and their native
runtime libraries. It does not change host security or network policy. Example
from the Peios workspace root:

```sh
python3 pkgs/dev.peios.peios-experimental/tests/transfer/run.py \
  --kernel pkm/out/build/kunit/arch/x86/boot/bzImage \
  --root /path/to/composed-system-root \
  --openssl-stage /path/to/composed-system-root \
  --rsync-stage /path/to/composed-system-root \
  --libpeios-static libpeios/target/release/libpeios.a \
  --work /tmp/new-transfer-run
```

The stage arguments also accept Pekit build stages during development. The work
directory must not exist. The runner requires a native SDK, static libpeios,
readelf, cpio and QEMU. The kernel needs built-in boot, tmpfs and native security
support. Serial output is saved as `transfer-vm.log`; success requires the final
`TRANSFER_PASS` marker and a clean QEMU exit.

Two ordinary tokens have distinct SIDs but identical projected UID/GID values.
The checks cover private creation and overwrite, key conversion, RNG/KDF and
mixed exports, decrypted plaintext (including CMS EncryptedData), unsafe
shared/link/FIFO/device destinations,
real TLS sessions and keylogs, strict hostname validation, and default CA-file
and hashed-directory trust lookup. Trust fixtures model trustd's output paths;
they do not run trustd or test its registry reconciliation.

Rsync checks native inheritance for new files, refusal when full destination
security cannot be preserved, explicit in-place updates, complete descriptor
preservation with an authorized token, ordinary data xattrs, and rejection of
archive preservation and daemon serving. A throttled transfer is killed after
its temporary inode appears, checking read denial both during the transfer and
after interruption, with no final destination published. Receiving through a
foreign-SID destination symlink is rejected even when its Unix UID is zero;
an own-SID link provides the positive control. A third token has the first SID plus
SeSecurity and SeRestore specifically to test full-descriptor replacement.
This does not grant those privileges to the installed tools.

The loopback TLS server uses the boot fixture's SYSTEM identity because the
minimal VM has no registry-loaded port-reservation seed. Clients use the ordinary
token. No PNP exception is installed. This fixture does not claim to exercise
per-tool PNP denial or SSH authentication; the existing PNP kernel tests and
OpenSSH qualification cover those separate boundaries. Portable upstream suites
run through each package's Pekit test gate, separately from these native checks.
