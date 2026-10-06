7.991: https://nmap.org/dist/nmap-7.991.tar.bz2
SHA-256: a5d507f29437bef3bedd4771ff9aaa8fc1c2a109ddba1f5b1cf12027456929be
Reviewed 2026-09-27 under PEI-1190.

The detached signature is retained alongside the official public key file from
https://nmap.org/data/nmap_gpgkeys.txt. GPG verifies the archive against primary
fingerprint 436D66AB9A798425FDA0E3F801AF9F036B9355D0, using legacy DSA/SHA-1.
Pekit's verification policy rejects this algorithm. Jack explicitly approved a
Nmap-only exception on 2026-09-27; the recipe pins the archive SHA-256 and the
lint exception is limited to this source. Pekit's global policy is unchanged.

Nmap uses NPSL 0.95. Its conservative catalogue license class is proprietary;
this is not a claim that the bundled MIT/BSD components are proprietary. Full
Nmap and bundled Lua, libdnet, liblinear and libssh2 notices ship in the runtime
package. The source package retains the complete upstream source and patches.
