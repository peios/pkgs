1.8.1.3: https://deb.debian.org/debian/pool/main/s/socat/socat_1.8.1.3.orig.tar.bz2
SHA-256: 25bc6476292b2e614220989c77b0b6fca87bb2525d9747b31a6639b1fb602418
Reviewed 2026-09-27 under PEI-1190.

The retained Debian socat_1.8.1.3-2.dsc authenticates this orig archive's digest.
GPG verifies its RSA/SHA-512 signature against Debian maintainer primary key
A0DF7E0D3851E0EE45C00BC8ACE1F33CB933BBBB (signing subkey
7D887DC8BA7BBBA7B835E3BADCE310E7864CC8BF), obtained from keyring.debian.org.
The key and DSC are retained here. Pekit's checksum parser does not parse DSC
metadata, so the recipe pins SHA-256 and records a source-specific lint exception.
Only the orig archive is used, without Debian patches. The upstream HTTPS
certificate failed validation and its alternate repository blocked this region;
no TLS verification bypass was used.
