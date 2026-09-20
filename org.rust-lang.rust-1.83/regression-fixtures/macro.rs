extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro]
pub fn checked_answer(input: TokenStream) -> TokenStream {
    assert_eq!(input.to_string(), "19 + 23");
    "42u32".parse().unwrap()
}
