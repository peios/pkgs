# `deps/` — vendored libpeios (temporary build bridge)

The Peios e2fsprogs patches link **libpeios** (the userspace C ABI):

- Patch 1 (`-E root_sddl=`/`root_sd_file=`) calls `peios_sddl_parse_sd()`.
- Patch 2 (`-d` SD-aware population) calls `peios_sd_reinherit()`.

Building `mke2fs` therefore needs libpeios's headers (to `#include
<peios/security.h>`, which in turn `#include`s the `pkm/` UAPI headers) and its
shared object (to link `-lpeios`).

Until the build root provides libpeios as a package (its `-devel` ships the
header + `.so` symlink + `peios.pc`), this directory **vendors** those artifacts
so the recipe's `build.main` compiles offline:

```
deps/
  include/peios.h, include/peios/*.h   libpeios public headers
  include/pkm/*.h                       pkm UAPI headers the peios headers #include
  lib/libpeios.so.0                     runtime shared object (SONAME libpeios.so.0)
  lib/libpeios.so -> libpeios.so.0      dev symlink for `-lpeios`
  lib/libpeios.a                        static archive (unused; mke2fs links the .so)
```

Populate with `./deps/refresh.sh` (builds libpeios release, then copies). The
recipe injects `-I deps/include -L deps/lib` into `CC` for `build.main`.

The produced `mke2fs` carries a normal `DT_NEEDED libpeios.so.0` and **no rpath**
— it resolves libpeios from the system path at runtime (what the packaged build
wants). To run it against this vendored copy locally, set
`LD_LIBRARY_PATH=deps/lib`.

When libpeios publishes `libpeios`/`libpeios-devel` as resolvable peipkg deps,
drop `deps/` and restore the `[build.main.dependencies.peipkg]` entries (the
cc-wrapper then injects `-I/-L` from the staged dep, same as gmp→mpfr).
