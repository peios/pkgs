// RUN: %clang_cc1 -std=c++17 -fsyntax-only %s
// RUN: %clang_cc1 -std=c++17 -fexperimental-new-constant-interpreter -fsyntax-only %s
// Narrow operands must not be promoted, and wide operands retain all bits.
using U65 = unsigned _BitInt(65);
using U128 = unsigned _BitInt(128);
using U257 = unsigned _BitInt(257);
static_assert(__builtin_popcountg((unsigned char)255) == 8);
static_assert(__builtin_clzg((unsigned char)1) == 7);
static_assert(__builtin_ctzg((unsigned char)128) == 7);
static_assert(__builtin_popcountg((unsigned __int128)-1) == 128);
static_assert(__builtin_clzg((unsigned __int128)1) == 127);
static_assert(__builtin_ctzg((unsigned __int128)1 << 127) == 127);
static_assert(__builtin_popcountg((U65)-1) == 65);
static_assert(__builtin_popcountg((U128)-1) == 128);
static_assert(__builtin_popcountg((U257)-1) == 257);
static_assert(__builtin_clzg((U257)1) == 256);
static_assert(__builtin_ctzg((U257)1 << 256) == 256);
static_assert(__builtin_clzg((U257)0, -7) == -7);
static_assert(__builtin_ctzg((U257)0, -11) == -11);
constexpr int fallback_effects() {
  int calls = 0;
  int result = __builtin_clzg((U257)1, ++calls);
  result += __builtin_ctzg((U257)1, ++calls);
  result += __builtin_clzg((U257)0, ++calls);
  result += __builtin_ctzg((U257)0, ++calls);
  return result == 263 && calls == 4;
}
static_assert(fallback_effects());
int main() {
  volatile unsigned _BitInt(1) one = 1;
  volatile unsigned _BitInt(2) two = 3;
  if (__builtin_popcountg(one) != 1 || __builtin_popcountg(two) != 2) return 7;
  volatile unsigned char byte = 255;
  volatile U257 wide = (U257)1 << 256;
  volatile U257 zero = 0;
  if (__builtin_popcountg(byte) != 8 || __builtin_clzg(byte) != 0 ||
      __builtin_ctzg(byte) != 0) return 1;
  if (__builtin_popcountg(wide) != 1 || __builtin_clzg(wide) != 0 ||
      __builtin_ctzg(wide) != 256) return 2;
  int calls = 0;
  if (__builtin_clzg(wide, ++calls) != 0 || calls != 1) return 3;
  if (__builtin_ctzg(wide, ++calls) != 256 || calls != 2) return 4;
  if (__builtin_clzg(zero, ++calls) != 3 || calls != 3) return 5;
  if (__builtin_ctzg(zero, ++calls) != 4 || calls != 4) return 6;
  return 0;
}
