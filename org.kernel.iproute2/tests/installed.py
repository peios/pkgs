import socket, subprocess, sys
ss = sys.argv[1]
subprocess.run([ss, '-V'], check=True)
for family, addr in [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')]:
    with socket.socket(family, socket.SOCK_STREAM) as s:
        s.bind((addr, 0)); s.listen()
        port = s.getsockname()[1]
        out = subprocess.check_output([ss, '-H', '-ltn', f'sport = :{port}'], text=True)
        assert f':{port}' in out, out
        empty = subprocess.check_output([ss, '-H', '-ltn', 'sport = :0'], text=True)
        assert not empty, empty
print('SS_INSTALLED_PASS')
