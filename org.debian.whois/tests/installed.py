"""Real WHOIS request/response against a local protocol fixture; no Internet."""
import socket, subprocess, sys, threading
binary=sys.argv[1]
assert '5.' in subprocess.check_output([binary,'--version'],text=True)
for family,host in [(socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')]:
    server=socket.socket(family);server.bind((host,0));server.listen();server.settimeout(5)
    request=[]
    def reply():
        conn,_=server.accept();conn.settimeout(5)
        with conn:
            data=b''
            while not data.endswith(b'\r\n'):data+=conn.recv(4096)
            request.append(data);conn.sendall(b'netname: PEIOS-TEST\r\n')
    thread=threading.Thread(target=reply);thread.start()
    result=subprocess.run([binary,'-h',host,'-p',str(server.getsockname()[1]),'192.0.2.1'],capture_output=True,text=True,timeout=10)
    thread.join(5);server.close()
    assert result.returncode==0,result.stderr
    assert 'PEIOS-TEST' in result.stdout,result.stdout
    assert request==[b'192.0.2.1\r\n'],request
# Invalid arguments fail rather than issuing an accidental default query.
assert subprocess.run([binary,'--not-a-real-option'],capture_output=True,timeout=5).returncode!=0
print('WHOIS: IPv4/IPv6 query bytes, response output and argument rejection passed')
