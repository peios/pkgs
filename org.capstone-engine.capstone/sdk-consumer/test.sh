#!/bin/sh
set -eu
: "${SDK_TEST_OUT:?}"
: "${PEKIT_MAIN_OUT:?}"
SDK="$SDK_TEST_OUT/projected-sdk"
CONSUMER="$SDK_TEST_OUT/sdk-consumer-build"
# The projection follows package file maps and only the SDK's declared family
# dependencies; unrelated staged files are absent. -devel depends on -static
# because its CMake export names libcapstone.a, so the archive must come
# from -static and nowhere else.
python3 "$PEKIT_RECIPE_ROOT/sdk-consumer/project-sdk.py" \
  --recipe "$PEKIT_RECIPE_ROOT" --stage "$PEKIT_MAIN_OUT" \
  --sdk "org.capstone-engine.capstone-devel" --out "$SDK"
python3 - "$SDK/projection.json" <<'EOF'
import json, sys
files = json.load(open(sys.argv[1]))['files']
owner = files['usr/lib/x86_64-linux-peios/libcapstone.a']['owner']
if owner != 'org.capstone-engine.capstone-static':
    raise SystemExit('libcapstone.a projected from ' + owner)
if any(p.endswith('.a') and r['owner'] != owner for p, r in files.items()):
    raise SystemExit('static archive outside the -static package')
EOF
export LD_LIBRARY_PATH="$SDK/usr/lib/x86_64-linux-peios:/usr/lib/x86_64-linux-peios"
cmake -S "$PEKIT_RECIPE_ROOT/sdk-consumer" -B "$CONSUMER" \
  -Dcapstone_DIR="$SDK/usr/lib/x86_64-linux-peios/cmake/capstone" \
  -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF -DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF
cmake --build "$CONSUMER" --parallel 2
test "$(ctest --test-dir "$CONSUMER" -N | sed -n 's/^Total Tests: //p')" -eq 3
ctest --test-dir "$CONSUMER" --output-on-failure
readelf -d "$CONSUMER/consumer-shared" | grep -F 'Shared library: [libcapstone.so.5]'
if readelf -d "$CONSUMER/consumer-static" | grep -F 'Shared library: [libcapstone.so.5]'; then
  echo 'static SDK consumer unexpectedly linked its shared counterpart' >&2
  exit 1
fi
printf '%s\n' 'SDK_CONSUMER_RESULT {"family":"org.capstone-engine.capstone","shared":true,"static":true,"tests":3,"static_package":"org.capstone-engine.capstone-static"}'
