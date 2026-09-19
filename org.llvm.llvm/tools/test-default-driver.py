#!/usr/bin/env python3
"""Compile, link and execute with the staged drivers and ordinary system SDK.

No include/library search overrides are permitted. LD_LIBRARY_PATH locates the
staged compiler's own DSOs only; the link commands use the driver defaults.
"""
import argparse, hashlib, json, os, signal, subprocess
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--prefix',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args(); prefix=a.prefix.resolve(); out=a.output.resolve()
out.mkdir(parents=True,exist_ok=False)
env=os.environ.copy()
for k in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH','LIBRARY_PATH','COMPILER_PATH','GCC_EXEC_PREFIX','CFLAGS','CPPFLAGS','CXXFLAGS','LDFLAGS','CLANG_CONFIG_FILE_SYSTEM_DIR','CLANG_CONFIG_FILE_USER_DIR'):
    env.pop(k,None)
env['LD_LIBRARY_PATH']=str(prefix/'lib/x86_64-linux-peios')
source_c=r'''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
  uint32_t *a = calloc(4, sizeof *a);
  assert(a); a[2] = 37;
  uint32_t b[4]; memcpy(b, a, sizeof b); free(a);
  assert(b[0] == 0 && b[2] == 37);
  puts("driver-c-ok"); return 0;
}
'''
source_cpp=r'''#include <atomic>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
struct NonPowerTwo {
  using result_type = unsigned;
  std::minstd_rand engine{7};
  static constexpr unsigned min() { return 1; }
  static constexpr unsigned max() { return 6; }
  unsigned operator()() { return 1 + engine() % 6; }
};
int main() {
  std::vector<int> values{1, 2, 3, 4};
  std::mt19937 random_engine{42};
  NonPowerTwo nonpower;
  double a = std::generate_canonical<double, 53>(random_engine);
  double b = std::generate_canonical<double, 53>(nonpower);
  double c = std::uniform_real_distribution<double>(0.0, 1.0)(random_engine);
  if (!(a >= 0 && a < 1 && b >= 0 && b < 1 && c >= 0 && c < 1)) return 3;
  std::string message = "driver-cxx-ok";
  std::atomic<int> total{0};
  std::thread worker([&] { total = std::accumulate(values.begin(), values.end(), 0); });
  worker.join();
#if __cplusplus >= 202002L
  std::atomic<int> ready{0};
  std::thread notifier([&] {
    ready.store(1, std::memory_order_release);
    ready.notify_all();
  });
  while (ready.load(std::memory_order_acquire) == 0)
    ready.wait(0, std::memory_order_acquire);
  notifier.join();
#endif
  if (total != 10 || message.substr(7) != "cxx-ok") return 1;
  try { throw std::runtime_error(message); }
  catch (const std::runtime_error &e) {
    if (e.what() != message) return 2;
    std::cout << e.what() << '\n'; return 0;
  }
}
'''
(out/'stdlib.c').write_text(source_c); (out/'stdlib.cpp').write_text(source_cpp)
result={'scope':'Actual staged default C/C++ driver compile/link/run; system SDK; no injected include/library paths','prefix':str(prefix),'compilers':{},'checks':[]}
def run(label,cmd,expected=None):
    from types import SimpleNamespace
    timeout=300 if label.endswith('-build') else 30
    child=subprocess.Popen(list(map(str,cmd)),env=env,cwd=out,text=True,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           start_new_session=True)
    try:
        output,_=child.communicate(timeout=timeout)
        r=SimpleNamespace(returncode=child.returncode,stdout=output)
    except subprocess.TimeoutExpired:
        try: os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        output,_=child.communicate()
        r=SimpleNamespace(returncode=124,stdout=output+'\nTimed out\n')
    (out/(label+'.log')).write_text(r.stdout)
    passed=r.returncode==0 and (expected is None or r.stdout==expected)
    result['checks'].append({'label':label,'command':list(map(str,cmd)),'returncode':r.returncode,'passed':passed,'log_sha256':hashlib.sha256(r.stdout.encode()).hexdigest()})
    return passed
for name in ['clang','clang++']:
    driver=prefix/'bin'/name
    result['compilers'][name]={'path':str(driver),'sha256':hashlib.file_digest(driver.open('rb'),'sha256').hexdigest()}
    run(name+'-version',[driver,'--version'])
run('default-search',[prefix/'bin/clang++','-v','-E','-x','c++','/dev/null'])
for label,driver,source,flags,expected in [
 ('c11','clang','stdlib.c',['-std=c11','-O2'],'driver-c-ok\n'),
 ('cxx17','clang++','stdlib.cpp',['-std=c++17','-O2','-pthread'],'driver-cxx-ok\n'),
 ('cxx20','clang++','stdlib.cpp',['-std=c++20','-O2','-pthread'],'driver-cxx-ok\n'),
 ('cxx17-normalized-target','clang++','stdlib.cpp',['--target=x86_64-unknown-linux-peios','-std=c++17','-O2','-pthread'],'driver-cxx-ok\n')]:
    if run(label+'-build',[prefix/'bin'/driver,*flags,out/source,'-o',out/label]):
        run(label+'-run',[out/label],expected)
result['passed']=all(c['passed'] for c in result['checks'])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['passed'] else 1)
