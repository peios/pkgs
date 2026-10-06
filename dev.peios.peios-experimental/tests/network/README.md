# Native networking qualification (PEI-1184)

The package workers execute upstream and installed-client tests on Linux.
The native identity and FACS checks require a Peios kernel. After publishing
and composing a fresh Experimental root, run from the workspace:

```sh
python3 pkgs/dev.peios.peios-experimental/tests/network/run.py \
  --kernel PATH/TO/PEIOS/bzImage \
  --root PATH/TO/COMPOSED/ROOT \
  --libpeios-static libpeios/target/release/libpeios.a \
  --work /tmp/network-qualification
```

The work directory must not exist. Host prerequisites are a C compiler,
`readelf`, `cpio` and QEMU. The test copies only the selected root's installed
clients and their libraries; it never uses host dynamic libraries. Use a kernel
with built-in initramfs, tmpfs, devtmpfs, IPv4 and IPv6 support. The PKM KUnit
profile supplies these; `kunit.enable=0` selects this guest test.

The fixture creates two native principals with the same projected UID/GID and
no privileges. It tests actual IPv4/IPv6 `ping`, continued denial of raw ICMP,
and an HTTP transfer whose cookie jar, HSTS cache and Alt-Svc cache are readable
by the owner and denied to the other SID. It uses a local server, not the Internet.

PNP's policy checks live in `pkm/pnp/kunit.c` and run through PKM's mandatory
KUnit gate: `pnp_kunit_echo_obeys_policy` covers Packet and RawPacket hooks and
the refusal-bypass counter; `pnp_kunit_echo_on_wire` sends real loopback echo,
then drops requests and replies independently inbound and outbound for IPv4
and IPv6. No registry policy or PNP exception is installed by this fixture.

For the composed clients' DNS/TCP/UDP/socket tests on the build host, use:

```sh
python3 pkgs/dev.peios.peios-experimental/tests/network/installed.py PATH/TO/COMPOSED/ROOT
```

This requires host Python and bubblewrap. Mock servers run on the host network;
each client runs in a namespace containing only the composed runtime root.
The native VM check above remains necessary for Peios authorization behavior.
