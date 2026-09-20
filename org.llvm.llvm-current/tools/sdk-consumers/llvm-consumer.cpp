#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Support/raw_ostream.h>
int main() {
  llvm::LLVMContext context; llvm::Module module("sdk-proof", context);
  auto *type = llvm::FunctionType::get(llvm::Type::getInt32Ty(context), false);
  auto *function = llvm::Function::Create(type, llvm::Function::ExternalLinkage, "answer", module);
  llvm::IRBuilder<> builder(llvm::BasicBlock::Create(context, "entry", function));
  builder.CreateRet(llvm::ConstantInt::get(llvm::Type::getInt32Ty(context), 42));
  if (llvm::verifyModule(module, &llvm::errs())) return 1;
  return module.getFunction("answer") == function ? 0 : 2;
}
