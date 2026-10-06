"""Installed iperf3 loopback TCP/UDP, reverse and parallel measurements."""
import json,os,socket,subprocess,sys,time
from pathlib import Path
stage=Path(sys.argv[1]);binary=stage/'usr/bin/iperf3'
env=dict(os.environ,LD_LIBRARY_PATH=str(stage/'usr/lib/x86_64-linux-peios'))
assert 'iperf 3.' in subprocess.check_output([binary,'--version'],env=env,text=True)
for options in ([],['-u','-b','1M'],['-R'],['-P','2'],['-6']):
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    server=subprocess.Popen([binary,'-s','-1','-p',str(port)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        time.sleep(.2)
        client=subprocess.run([binary,'-c','::1' if '-6' in options else '127.0.0.1','-p',str(port),'-t','1','-J',*options],env=env,capture_output=True,text=True,timeout=15)
        assert client.returncode==0,(options,client.stdout,client.stderr)
        result=json.loads(client.stdout);assert 'error' not in result,result
        assert result['end']['streams'],result
        out,err=server.communicate(timeout=10);assert server.returncode==0,(out,err)
    finally:
        if server.poll() is None:server.kill();server.wait()
print('iperf3: TCP, UDP, reverse, parallel and IPv6 installed tests passed')
