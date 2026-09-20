#include <clang/AST/Decl.h>
#include <clang/AST/Expr.h>
#include <clang/AST/Stmt.h>
#include <clang/Basic/Diagnostic.h>
#include <clang/Basic/SourceManager.h>
#include <clang/Frontend/ASTUnit.h>
#include <clang/Tooling/Tooling.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/raw_ostream.h>
#include <string>

int main() {
  using namespace clang;
  using namespace clang::tooling;
  const std::string code =
      "int peios_sdk_probe() { return 42; }\n"
      "int peios_sdk_caller() { return peios_sdk_probe(); }\n";
  auto ast = buildASTFromCodeWithArgs(code, {"-std=c++17"}, "probe.cc");
  if (!ast || ast->getDiagnostics().hasErrorOccurred())
    return 11;
  const FunctionDecl *probe = nullptr, *caller = nullptr;
  for (const auto *decl : ast->getASTContext().getTranslationUnitDecl()->decls()) {
    const auto *function = llvm::dyn_cast<FunctionDecl>(decl);
    if (!function || !function->hasBody() ||
        !function->getReturnType()->isIntegerType())
      continue;
    if (function->getNameAsString() == "peios_sdk_probe")
      probe = function;
    if (function->getNameAsString() == "peios_sdk_caller")
      caller = function;
  }
  if (!probe || !caller)
    return 12;
  const auto *body = llvm::dyn_cast<CompoundStmt>(caller->getBody());
  if (!body || body->size() != 1)
    return 13;
  const auto *ret = llvm::dyn_cast<ReturnStmt>(*body->body_begin());
  const auto *call = ret && ret->getRetValue()
      ? llvm::dyn_cast<CallExpr>(ret->getRetValue()->IgnoreParenImpCasts()) : nullptr;
  if (!call || call->getDirectCallee() != probe)
    return 14;
  const unsigned begin = code.rfind("peios_sdk_probe()");
  const unsigned end = begin + std::string("peios_sdk_probe(").size();
  const auto &sources = ast->getSourceManager();
  const auto *probeBody = llvm::dyn_cast<CompoundStmt>(probe->getBody());
  if (!probeBody || probeBody->size() != 1)
    return 15;
  const auto *probeReturn = llvm::dyn_cast<ReturnStmt>(*probeBody->body_begin());
  const auto *literal = probeReturn && probeReturn->getRetValue()
      ? llvm::dyn_cast<IntegerLiteral>(probeReturn->getRetValue()->IgnoreParenImpCasts())
      : nullptr;
  if (!literal || literal->getValue() != 42)
    return 16;
  const auto hasOffset = [&](SourceLocation location, unsigned expected) {
    return location.isValid() && sources.isWrittenInMainFile(location) &&
        sources.getFileOffset(location) == expected;
  };
  const auto range = call->getSourceRange();
  if (!hasOffset(call->getBeginLoc(), begin) ||
      !hasOffset(call->getExprLoc(), begin) ||
      !hasOffset(call->getEndLoc(), end) ||
      !hasOffset(call->getRParenLoc(), end) ||
      !hasOffset(range.getBegin(), begin) ||
      !hasOffset(range.getEnd(), end) ||
      !hasOffset(probe->getLocation(), code.find("peios_sdk_probe")) ||
      !hasOffset(literal->getBeginLoc(), code.find("42"))) {
    llvm::errs() << "Installed AST source locations are incorrect\n";
    return 17;
  }
  const auto presumed = sources.getPresumedLoc(call->getBeginLoc());
  const auto secondLine = code.find('\n') + 1;
  if (presumed.isInvalid() || std::string(presumed.getFilename()) != "probe.cc" ||
      presumed.getLine() != 2 || presumed.getColumn() != begin - secondLine + 1 ||
      sources.getBufferData(sources.getMainFileID()) != code) {
    llvm::errs() << "Installed source manager returned incorrect file/line/buffer data\n";
    return 18;
  }
  llvm::outs() << "Installed AST structure and source locations passed\n";
  return 0;
}
