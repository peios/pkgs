# `_pybuild_` — the Python packaging policy, in one place

Peios ships no pip, so every Python recipe would otherwise hand-roll the same
four steps: call a PEP 517 backend, extract the wheel, generate the console
scripts, compile the bytecode. `install-wheel` is those steps, so that the
*policy* — one site-packages, checked-hash bytecode, `#!/bin/python3`
launchers (and module shebangs rewritten to match, before compiling), private
modules for applications — lives here rather than in each
recipe, and a new recipe cannot quietly get one of them wrong.

It is a workspace helper, not a package, for the same reason `_peiroot_/` is:
`flit_core` is the first Python package in the pool and could not depend on a
tool that is itself installed this way. Recipes reach it through
`$PEKIT_WORKSPACE_ROOT`, which the build sandbox binds at its host path.

    python3 "$PEKIT_WORKSPACE_ROOT/_pybuild_/install-wheel" \
        --backend flit_core.buildapi --out "$PEKIT_OUT" .

Third-party recipes outside this workspace cannot use it; the steps it
performs are documented for them under Developing for Peios -> Shipping
software -> Python packages.

Python recipes build only in the native Peios root. Library wheels are staged
below `/usr/lib/x86_64-linux-peios/pythonX.Y/site-packages`, using the
executing interpreter's major/minor version, and the interpreter must report
exactly that path through sysconfig. `install-wheel` verifies the wheel's
RECORD before extracting it.
