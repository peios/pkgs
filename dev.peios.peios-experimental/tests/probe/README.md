# Native capture, relay and probing qualification

`run.py` boots the production Peios kernel with packaged tools and their runtime
closure. Supply a JSON object mapping the seven package names to stages or to a
freshly composed Experimental root. For published qualification, every value
must name that composed root. `--pcap-sdk` supplies headers only; the helper
links against the runtime library from the mapped root.

```sh
python3 tests/probe/run.py \
  --kernel /absolute/path/to/peios/vmlinuz \
  --root /absolute/path/to/composed/root \
  --stages /absolute/path/to/packages.json \
  --pcap-sdk /absolute/path/to/libpcap/build/main \
  --libpeios-static /absolute/path/to/libpeios.a \
  --work /absolute/path/to/new/output
```

The fixture installs primary tokens before exec. Distinct native principals
share projected UID 1000; an explicitly privileged fixture token has enabled
SeTcbPrivilege. Checks cover ordinary and authorized probing, IPv4/IPv6 routes,
MTR reports, live and offline capture, private capture creation and append,
cross-principal denial, refusal of unsafe capture destinations, Nmap's automatic
connect/raw selection and private XML output, ordinary raw-scan denial, ARP on
the QEMU link, socat file/TCP/TLS/PTY relays and unsupported option rejection.
TLS checks include an IP SAN match and a rejected peer-name mismatch.

SYSTEM fixture servers use the kernel's fixed-port fallback because this minimal
boot does not load registry seeds. The privileged token is a test fixture only;
none of these packages grants it. QEMU user networking uses `restrict=on`; ARP
targets its virtual gateway and other tests use loopback. Devpts uses native
ephemeral descriptor synthesis rather than unsupported per-inode SD updates.

This tests native tool semantics and socket authority, not a full installation
boot, physical network performance or per-tool PNP denial rules. PNP policy
enforcement qualification is separate. No policy or kernel changes are made.

Success requires `PROBE_PASS`, no `PROBE_FAIL`, and a clean QEMU exit. Runs use a
new ignored output directory, have a bounded timeout and never retry boots.
