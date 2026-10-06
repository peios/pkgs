"""Installed protocol and parser tests; live privileged cases run in Peios VM."""
import ctypes as C,os,socket,struct,subprocess,sys,threading
from pathlib import Path
stage=Path(sys.argv[1]);pkg=Path(__file__).resolve().parents[1].name
env=dict(os.environ,LD_LIBRARY_PATH=str(stage/'usr/lib/x86_64-linux-peios'),OPENSSL_CONF='/dev/null')
def run(args,**kw):
 r=subprocess.run([str(stage/'usr/bin'/args[0]),*args[1:]],env=env,capture_output=True,timeout=15,**kw)
 assert r.returncode==0,(args,r.stdout,r.stderr);return r.stdout
if pkg=='org.tcpdump.libpcap':
 symbols=subprocess.check_output(['readelf','--dyn-syms','--wide',str(stage/'usr/lib/x86_64-linux-peios/libpcap.so')],text=True)
 assert 'peios_file_open' in symbols, 'Native FACS implementation was not linked'
 lib=C.CDLL(str(stage/'usr/lib/x86_64-linux-peios/libpcap.so'))
 class BPF(C.Structure):_fields_=[('length',C.c_uint),('insns',C.c_void_p)]
 lib.pcap_open_dead.restype=C.c_void_p;lib.pcap_open_dead.argtypes=[C.c_int,C.c_int]
 lib.pcap_compile.argtypes=[C.c_void_p,C.POINTER(BPF),C.c_char_p,C.c_int,C.c_uint]
 lib.pcap_freecode.argtypes=[C.POINTER(BPF)];lib.pcap_close.argtypes=[C.c_void_p]
 p=lib.pcap_open_dead(1,65535);assert p
 for expression in [b'tcp port 443',b'ip6 and udp',b'arp',b'not host 192.0.2.1']:
  b=BPF();assert lib.pcap_compile(p,C.byref(b),expression,1,0xffffffff)==0;assert b.length>0;lib.pcap_freecode(C.byref(b))
 b=BPF();assert lib.pcap_compile(p,C.byref(b),b'tcp and (',1,0xffffffff)!=0;lib.pcap_close(p)
elif pkg=='org.tcpdump.tcpdump':
 # One Ethernet+IPv4 UDP frame from documentation addresses, decoded offline.
 frame=bytes.fromhex('ffffffffffff02000000000108004500001c0001000040110000c0000201c000020204d2003500080000')
 fixture=struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1)+struct.pack('<IIII',0,0,len(frame),len(frame))+frame
 out=run(['tcpdump','-nn','-r','-'],input=fixture);assert b'192.0.2.1.1234 > 192.0.2.2.53' in out,out
 r=subprocess.run([stage/'usr/bin/tcpdump','-Z','nobody','-r','-'],env=env,input=fixture,capture_output=True);assert r.returncode!=0 and b'unsupported' in r.stderr
elif pkg=='org.dest-unreach.socat':
 assert run(['socat','-u','-','EXEC:/bin/cat'],input=b'PEIOS-relay\n')==b'PEIOS-relay\n'
 for option in ['setuid=0','su=nobody','mode=0600','user=0','umask=077']:
  r=subprocess.run([stage/'usr/bin/socat','-u','-','OPEN:/tmp/must-not-exist,'+option],env=env,input=b'x',capture_output=True);assert r.returncode!=0 and b'unsupported on Peios' in r.stderr,(option,r.stderr)
elif pkg=='nl.bitwizard.mtr':
 assert b'mtr' in run(['mtr','--version']).lower()
 # Actual privileged/ordinary helper protocol tests belong in the native VM.
 r=subprocess.run([stage/'usr/bin/mtr','--not-a-real-option'],env=env,capture_output=True);assert r.returncode!=0
elif pkg=='net.sourceforge.traceroute':
 out=run(['traceroute','-n','-m','1','-q','1','-w','1','127.0.0.1']);assert b'127.0.0.1' in out
 out=run(['traceroute','-6','-n','-m','1','-q','1','-w','1','::1']);assert b'::1' in out
elif pkg=='org.nmap.nmap':
 s=socket.socket();s.bind(('127.0.0.1',0));s.listen();port=s.getsockname()[1]
 out=run(['nmap','--unprivileged','--datadir',str(stage/'usr/share/nmap'),'-sT','-Pn','-n','-p',str(port),'127.0.0.1','-oX','-']);s.close()
 assert b'state="open"' in out and b'<nmaprun' in out,out
else:raise AssertionError(pkg)
print(pkg+': installed protocol/parser checks passed')
