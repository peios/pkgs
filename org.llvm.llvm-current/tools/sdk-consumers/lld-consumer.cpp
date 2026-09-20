#include <lld/Common/Driver.h>
#include <llvm/ADT/ArrayRef.h>
#include <llvm/Support/raw_ostream.h>
#include <array>
#include <fstream>

LLD_HAS_DRIVER(elf)

int main(int argc, char **argv) {
  if (argc != 3)
    return 2;
  const char *arguments[] = {"ld.lld", "-m", "elf_x86_64", "-e", "_start",
                            "-o", argv[2], argv[1]};
  lld::DriverDef drivers[] = {{lld::Gnu, &lld::elf::link}};
  auto result = lld::lldMain(arguments, llvm::outs(), llvm::errs(), drivers);
  if (result.retCode != 0)
    return result.retCode;
  std::ifstream output(argv[2], std::ios::binary);
  std::array<unsigned char, 64> header{};
  if (!output.read(reinterpret_cast<char *>(header.data()), header.size()))
    return 3;
  // Real x86_64 little-endian ET_EXEC, not just a successful --version call.
  if (header[0] != 0x7f || header[1] != 'E' || header[2] != 'L' ||
      header[3] != 'F' || header[4] != 2 || header[5] != 1 ||
      header[16] != 2 || header[17] != 0 || header[18] != 62 || header[19] != 0)
    return 4;
  return 0;
}
