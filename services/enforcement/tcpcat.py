"""Persistent TCP catcher for the redirect demo: listen on the given
address, keep accepting connections, and append every received byte to the
output file with a per-connection marker. Runs until killed. Serves as the
forensic sink and the fake C2 service. argv: bind_addr port outfile"""

import socket
import sys
import threading

bind, port, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
lock = threading.Lock()


def handle(conn, peer):
    # No recv timeout: a forensic sink holds idle connections — the
    # daemon's redirect bridge may sit quiet for minutes between
    # redirected flows, and dropping its connection on idleness strands
    # redirected payloads on a dead socket.
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            with lock:
                with open(out, "ab") as fh:
                    fh.write(data)
    except OSError:
        pass
    finally:
        conn.close()


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((bind, port))
srv.listen(4)
with lock:
    with open(out, "ab") as fh:
        fh.write(f"[listening on {bind}:{port}]\n".encode())
while True:
    conn, peer = srv.accept()
    threading.Thread(target=handle, args=(conn, peer), daemon=True).start()
