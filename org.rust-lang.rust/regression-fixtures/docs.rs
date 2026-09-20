//! Installed rustdoc regression fixture.
//!
//! ```
//! assert_eq!((1..=10).sum::<i32>(), 55);
//! ```
//!
//! ```compile_fail
//! let value: u32 = "this must not typecheck";
//! ```
//!
//! ```should_panic
//! panic!("expected doctest panic");
//! ```
/// A documented value whose generated page must exist.
pub fn documented_value() -> u32 { 42 }
