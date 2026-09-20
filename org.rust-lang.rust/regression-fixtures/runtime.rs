use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;

struct Dropped(Arc<AtomicUsize>);
impl Drop for Dropped {
    fn drop(&mut self) { self.0.fetch_add(1, Ordering::SeqCst); }
}
fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    let drops = Arc::new(AtomicUsize::new(0));
    let result = catch_unwind(AssertUnwindSafe(|| {
        let _guard = Dropped(drops.clone());
        let values: Vec<_> = (0..1000).map(|v| v * v).collect();
        assert_eq!(values[999], 998001);
        panic!("expected unwind");
    }));
    assert!(result.is_err());
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    let counter = Arc::new(AtomicUsize::new(0));
    let workers: Vec<_> = (0..4).map(|_| {
        let counter = counter.clone();
        thread::spawn(move || {
            for _ in 0..1000 {
                let mut old = counter.load(Ordering::Acquire);
                loop {
                    match counter.compare_exchange_weak(old, old + 1, Ordering::AcqRel, Ordering::Acquire) {
                        Ok(_) => break,
                        Err(value) => old = value,
                    }
                }
            }
        })
    }).collect();
    for worker in workers { worker.join().unwrap(); }
    assert_eq!(counter.load(Ordering::SeqCst), 4000);
    let panicked = thread::spawn(|| panic!("expected child panic"));
    assert!(panicked.join().is_err());
    #[cfg(target_arch = "x86_64")]
    unsafe {
        use std::arch::x86_64::*;
        let vector = _mm_setr_epi32(1, 2, 3, 4);
        let doubled = _mm_add_epi32(vector, vector);
        let mut result = [0i32; 4];
        _mm_storeu_si128(result.as_mut_ptr().cast(), doubled);
        assert_eq!(result, [2, 4, 6, 8]);
    }
}
