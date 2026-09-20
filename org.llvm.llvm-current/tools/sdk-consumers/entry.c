/* Minimal x86_64 Linux entry point for the LLD SDK consumer's linked ELF. */
__attribute__((noreturn)) void _start(void) {
    __asm__ volatile("mov $60, %%eax\n\txor %%edi, %%edi\n\tsyscall"
                     : : : "rax", "rdi", "rcx", "r11", "memory");
    __builtin_unreachable();
}
