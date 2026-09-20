#!/bin/sh
# Install-only bootstrap sanity requires a path, but this recipe does not claim
# FileCheck comparisons. Fail closed if a new build/test path starts using it.
echo 'rust: this gate does not provide LLVM FileCheck; declare the real tool before enabling FileCheck tests' >&2
exit 1
