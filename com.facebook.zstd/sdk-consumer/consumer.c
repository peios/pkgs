#include <string.h>
#include <zstd.h>
int main(void) {
    const char input[] = "Peios projected SDK compression round trip";
    char encoded[256], decoded[256];
    size_t size = ZSTD_compress(encoded, sizeof encoded, input, sizeof input, 3);
    if (ZSTD_isError(size)) return 1;
    size_t result = ZSTD_decompress(decoded, sizeof decoded, encoded, size);
    if (ZSTD_isError(result) || result != sizeof input) return 2;
    return memcmp(input, decoded, sizeof input) != 0;
}
