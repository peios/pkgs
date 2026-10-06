# Nano validation

`pekit test --version 9.2` runs upstream `make check` and drives the staged
binary through a pseudo-terminal: editing, writing, preserving hardlinks and
creating a document. It runs in the native package root on the host kernel.

Before publication, also run `test-facs.sh` with a current Peios kernel,
staged nano, its patched source, the matching libpeios checkout (including its
host static library), PKM UAPI headers and a freshly composed runtime root.
All six inputs are positional and explicit; the script never downloads them.
Set `NANO_FACS_LOG` to retain the guest log at a chosen path.

The disposable guest creates two unprivileged SID identities sharing the same
numeric UID/GID. It checks private files in a permissively inheriting parent,
state directory validation, history round trips, symlink/hardlink rejection,
and rejection before truncation of a mode-0600 file with a public DACL. It
then runs the staged nano on a PTY as an unprivileged principal, verifying
in-place save and full SD preservation without READ_CONTROL/WRITE_DAC/WRITE_OWNER
on the document, plus backups, history and SIGHUP recovery. A second principal
must not read the backup or recovery file.

The guest's privileged harness prepares mount policies, test tokens and attack
fixtures. Nano receives no extra privileges. This is a focused kernel/runtime
test, not a claim that an Experimental installation ISO was boot-tested.
