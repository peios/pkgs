#[repr(C)]
struct Pair { x: i64, y: i64 }
extern "C" {
    fn peios_ffi_transform(input: Pair, callback: extern "C" fn(i64) -> i64) -> Pair;
    fn peios_ffi_size() -> usize;
}
extern "C" fn callback(value: i64) -> i64 { value * 3 }
fn main() {
    unsafe {
        assert_eq!(peios_ffi_size(), std::mem::size_of::<Pair>());
        let result = peios_ffi_transform(Pair { x: 7, y: 11 }, callback);
        assert_eq!((result.x, result.y), (33, 18));
    }
}
