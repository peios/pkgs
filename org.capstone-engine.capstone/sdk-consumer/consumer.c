#include <capstone/capstone.h>
#include <string.h>
int main(void) {
    csh handle;
    cs_insn *instructions;
    const unsigned char code[] = {0x55, 0x48, 0x89, 0xe5};
    if (cs_open(CS_ARCH_X86, CS_MODE_64, &handle) != CS_ERR_OK) return 1;
    size_t count = cs_disasm(handle, code, sizeof code, 0x1000, 0, &instructions);
    if (count != 2) return 2;
    int bad = strcmp(instructions[0].mnemonic, "push") ||
        strcmp(instructions[1].mnemonic, "mov") ||
        instructions[0].size != 1 || instructions[1].size != 3;
    cs_free(instructions, count);
    if (cs_close(&handle) != CS_ERR_OK) return 3;
    return bad != 0;
}
