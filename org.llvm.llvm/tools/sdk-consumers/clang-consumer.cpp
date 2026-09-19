#include <clang/AST/Decl.h>
#include <clang/AST/Expr.h>
#include <clang/AST/Stmt.h>
#include <clang/Basic/Diagnostic.h>
#include <clang/Basic/SourceManager.h>
#include <clang/Frontend/ASTUnit.h>
#include <clang/Tooling/NodeIntrospection.h>
#include <clang/Tooling/Tooling.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/raw_ostream.h>
#include <string>

static bool statementLocations(const clang::tooling::NodeLocationAccessors &data,
                               const clang::SourceManager &sources,
                               unsigned begin, unsigned end) {
  bool beginFound = false, endFound = false, expressionFound = false,
       parenFound = false, rangeFound = false;
  for (const auto &entry : data.LocationAccessors) {
    if (entry.first.isInvalid() || !sources.isWrittenInMainFile(entry.first))
      continue;
    const auto offset = sources.getFileOffset(entry.first);
    const auto name = clang::tooling::LocationCallFormatterCpp::format(*entry.second);
    beginFound |= name == "getBeginLoc()" && offset == begin;
    endFound |= name == "getEndLoc()" && offset == end;
    expressionFound |= name == "getExprLoc()" && offset == begin;
    parenFound |= name == "getRParenLoc()" && offset == end;
  }
  for (const auto &entry : data.RangeAccessors)
    if (entry.first.isValid() &&
        sources.isWrittenInMainFile(entry.first.getBegin()) &&
        sources.isWrittenInMainFile(entry.first.getEnd()) &&
        sources.getFileOffset(entry.first.getBegin()) == begin &&
        sources.getFileOffset(entry.first.getEnd()) == end)
      rangeFound = true;
  return beginFound && endFound && expressionFound && parenFound && rangeFound;
}

int main() {
  using namespace clang;
  using namespace clang::tooling;
  if (!NodeIntrospection::hasIntrospectionSupport()) {
    llvm::errs() << "Required installed AST introspection is unavailable\n";
    return 10;
  }
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
  const auto *call = ret ? llvm::dyn_cast<CallExpr>(ret->getRetValue()->IgnoreParenImpCasts()) : nullptr;
  if (!call || call->getDirectCallee() != probe)
    return 14;
  const unsigned begin = code.rfind("peios_sdk_probe()");
  const unsigned end = begin + std::string("peios_sdk_probe(").size();
  const auto &sources = ast->getSourceManager();
  if (!statementLocations(NodeIntrospection::GetLocations(call), sources, begin, end) ||
      !statementLocations(NodeIntrospection::GetLocations(DynTypedNode::create(*call)),
                          sources, begin, end)) {
    llvm::errs() << "Installed statement introspection returned incorrect locations\n";
    return 15;
  }
  const auto declLocations = NodeIntrospection::GetLocations(probe);
  bool declarationNameFound = false;
  for (const auto &entry : declLocations.LocationAccessors)
    declarationNameFound |= entry.first.isValid() &&
        sources.isWrittenInMainFile(entry.first) &&
        sources.getFileOffset(entry.first) == code.find("peios_sdk_probe");
  if (!declarationNameFound) {
    llvm::errs() << "Installed declaration introspection omitted the function name\n";
    return 16;
  }
  llvm::outs() << "Installed AST parsing and declaration/statement introspection passed\n";
  return 0;
}
