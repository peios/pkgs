struct Pair { long long x; long long y; };
struct Pair peios_ffi_transform(struct Pair input, long long (*callback)(long long)) {
    struct Pair result = { callback(input.y), input.x + input.y };
    return result;
}
unsigned long peios_ffi_size(void) { return sizeof(struct Pair); }
