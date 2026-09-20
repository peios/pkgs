"""Remove the build-only lit location from installed, relocatable SDK metadata."""
from pathlib import Path
import re
import sys
prefix, build = map(Path, sys.argv[1:])
config = prefix/'lib/x86_64-linux-peios/cmake/llvm/LLVMConfig.cmake'
text = config.read_text()
pattern = r'^set\(LLVM_DEFAULT_EXTERNAL_LIT "([^"\n]*)"\)$'
matches = list(re.finditer(pattern, text, re.M))
if len(matches) != 1:
    raise SystemExit('Expected exactly one LLVM_DEFAULT_EXTERNAL_LIT setting')
location = Path(matches[0].group(1))
if location.resolve() != (build/'bin/llvm-lit').resolve():
    raise SystemExit('Unexpected external lit location: '+str(location))
# Downstream test suites may explicitly set LLVM_EXTERNAL_LIT or discover lit.
# The compiler SDK does not install the build tree's Python lit wrapper.
config.write_text(re.sub(pattern, 'set(LLVM_DEFAULT_EXTERNAL_LIT "")', text, flags=re.M))
for path in (prefix/'lib/x86_64-linux-peios/cmake').rglob('*.cmake'):
    if str(build) in path.read_text():
        raise SystemExit('Installed CMake metadata leaks its build tree: '+str(path))
