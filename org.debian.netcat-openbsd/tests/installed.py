import socket, subprocess, sys, threading
nc = sys.argv[1]
for family, addr, flag in [(socket.AF_INET, '127.0.0.1', '-4'), (socket.AF_INET6, '::1', '-6')]:
    for kind, extra in [(socket.SOCK_STREAM, []), (socket.SOCK_DGRAM, ['-u'])]:
        with socket.socket(family, kind) as s:
            s.bind((addr, 0)); port=s.getsockname()[1]; s.settimeout(5)
            if kind==socket.SOCK_STREAM: s.listen()
            results=[]
            def server():
                if kind==socket.SOCK_STREAM:
                    with s.accept()[0] as c:
                        results.append(c.recv(4096)); c.sendall(b'ack\n')
                else:
                    data, peer=s.recvfrom(4096); results.append(data); s.sendto(b'ack\n',peer)
            t=threading.Thread(target=server);t.start()
            p=subprocess.run([nc,flag,*extra,'-w','1',addr,str(port)],input=b'probe\n',capture_output=True,timeout=6)
            t.join(6)
            assert results==[b'probe\n'] and p.stdout==b'ack\n' and p.returncode==0, (results,p)
print('NC_INSTALLED_PASS')
