# Native WHOIS and iperf3 qualification

`run.py` boots the production Peios kernel with the staged or published tools
and the runtime closure from a composed Experimental root. It compiles `guest.c`
against libpeios and copies the dynamically loaded GCC unwinder explicitly.
Use a new ignored output directory for each run:

```sh
python3 tests/measure/run.py \
  --kernel /absolute/path/to/peios/vmlinuz \
  --root /absolute/path/to/composed/root \
  --whois-stage /absolute/path/to/composed/root \
  --iperf-stage /absolute/path/to/composed/root \
  --libpeios-static /absolute/path/to/libpeios.a \
  --work /absolute/path/to/new/output
```

The fixture checks IPv4/IPv6 WHOIS wire queries and replies; iperf3 TCP, UDP,
reverse, parallel and IPv6 transfers; RSA authentication without plaintext
credential logging; owner-only PID and received-file access; refusal to truncate
a shared receive destination; and rejection of an ordinary fixed-port listener.
It gives two distinct native SIDs the same projected UID, installs their primary
tokens before exec, and checks cross-SID denial. Ordinary clients run without
privileges and with an inaccessible TMPDIR, exercising anonymous stream buffers.

Fixture servers run as SYSTEM because this minimal boot has no registry seeds
and retains the kernel's SYSTEM-only fixed-port fallback. It does not grant
production port authority or install packet-policy exceptions. The negative
listener case verifies native port authority, not a PNP packet-denial rule.
Existing PNP enforcement qualification remains separate. This is a loopback
protocol/security test, not a hardware throughput benchmark or full image boot.

Success requires `MEASURE_PASS`, no `MEASURE_FAIL`, and a clean QEMU exit. The
runner has a bounded timeout and does not retry boots.
