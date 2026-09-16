# libpeios ABI0 reference prerequisite

This is the original signed published source package 0.5.0-1, independently
verified against the included repository public key. `provenance.json` records
its exact archive and embedded-source hashes, origin commit and signature audit.
The mandatory acquisition target verifies those hashes before extraction.
The MIT licence is included beside the unchanged original package.

The package uses the older source format and contains no vendored closure.
Acquisition therefore runs its original Cargo.lock-bound vendor command and
preserves the matching PKM UAPI; the entire result becomes an explicit build
prerequisite and is included in the e2fsprogs source evidence. The offline Debian
SDK build and existing libpeios gates use those fixed inputs. Live first-party
sources and published packages are not changed.

This snapshot establishes the reference ABI0 used by the e2fsprogs extension.
Refresh it when that extension requires a newer libpeios API or when reference
prerequisite maintenance requires a security update. It does not pin the native
or runtime libpeios dependency to this package version.
