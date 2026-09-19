// RUN: not %clang_cc1 -std=c++17 -ferror-limit 0 -fsyntax-only %s 2>&1 | FileCheck %s
// RUN: not %clang_cc1 -std=c++17 -ferror-limit 0 -fexperimental-new-constant-interpreter -fsyntax-only %s 2>&1 | FileCheck %s
// CHECK-COUNT-8: error: constexpr variable '{{.*}}' must be initialized by a constant expression
// CHECK-NOT: error:
// Checked by the package gate for all eight named errors and absence of crash
// markers, and separately under a validated reference-provider leak detector.
constexpr int valid_before = __builtin_popcountg((unsigned _BitInt(257))-1);
static_assert(valid_before == 257);
constexpr int nested_clz_0(unsigned __int128 x) { return 5 + __builtin_clzg(x); }
constexpr int invalid_clz_0 = nested_clz_0(0);
constexpr int nested_ctz_0(unsigned __int128 x) { return 5 + __builtin_ctzg(x); }
constexpr int invalid_ctz_0 = nested_ctz_0(0);
constexpr int nested_clz_1(unsigned _BitInt(65) x) { return 5 + __builtin_clzg(x); }
constexpr int invalid_clz_1 = nested_clz_1(0);
constexpr int nested_ctz_1(unsigned _BitInt(65) x) { return 5 + __builtin_ctzg(x); }
constexpr int invalid_ctz_1 = nested_ctz_1(0);
constexpr int nested_clz_2(unsigned _BitInt(128) x) { return 5 + __builtin_clzg(x); }
constexpr int invalid_clz_2 = nested_clz_2(0);
constexpr int nested_ctz_2(unsigned _BitInt(128) x) { return 5 + __builtin_ctzg(x); }
constexpr int invalid_ctz_2 = nested_ctz_2(0);
constexpr int nested_clz_3(unsigned _BitInt(257) x) { return 5 + __builtin_clzg(x); }
constexpr int invalid_clz_3 = nested_clz_3(0);
constexpr int nested_ctz_3(unsigned _BitInt(257) x) { return 5 + __builtin_ctzg(x); }
constexpr int invalid_ctz_3 = nested_ctz_3(0);
constexpr int valid_after = __builtin_ctzg((unsigned _BitInt(257))1 << 256);
static_assert(valid_after == 256);
