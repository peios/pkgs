import socket, struct, subprocess, sys, threading
cmd=sys.argv[1]
subprocess.run([cmd,'-v'],check=True)
for family,addr in [(socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')]:
    for tcp in [False,True]:
        with socket.socket(family,socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as s:
            s.bind((addr,0));port=s.getsockname()[1];s.settimeout(8)
            if tcp:s.listen()
            def server():
                if tcp:
                    c,_=s.accept();c.settimeout(5)
                    n=struct.unpack('!H',c.recv(2))[0];q=b''
                    while len(q)<n:q+=c.recv(n-len(q))
                else:q,peer=s.recvfrom(4096)
                # Echo the question and return one fixed A record. No Internet.
                end=12
                while q[end]:end+=q[end]+1
                end+=5
                answer=q[:2]+struct.pack('!HHHHH',0x8180,1,1,0,0)+q[12:end]+b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+socket.inet_aton('192.0.2.42')
                if tcp:c.sendall(struct.pack('!H',len(answer))+answer);c.close()
                else:s.sendto(answer,peer)
            t=threading.Thread(target=server);t.start()
            out=subprocess.check_output([cmd,'@'+addr,'-p',str(port),'fixture.invalid','A','+short','+noedns','+tries=1','+time=3',*(['+tcp'] if tcp else [])],text=True,timeout=8)
            t.join(8);assert out.strip()=='192.0.2.42',out
print('DIG_INSTALLED_PASS')
