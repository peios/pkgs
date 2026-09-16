#!/bin/sh
set -eu
: "${SDK_TEST_OUT:?}"
: "${PEKIT_MAIN_OUT:?}"
SDK="$SDK_TEST_OUT/projected-sdk"
CONSUMER="$SDK_TEST_OUT/sdk-consumer-build"
# The projection follows package file maps and only the SDK's declared family
# dependencies. The optional static umbrella and unrelated staged tools are absent.
python3 "$PEKIT_RECIPE_ROOT/sdk-consumer/project-sdk.py" \
  --recipe "$PEKIT_RECIPE_ROOT" --stage "$PEKIT_MAIN_OUT" \
  --sdk "org.capstone-engine.capstone-devel" --out "$SDK"
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
printf '%s\n' 'SDK_CONSUMER_RESULT {"family":"org.capstone-engine.capstone","shared":true,"static":true,"tests":3,"optional_static_package":false}'
