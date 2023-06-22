import os
import argparse
import signal
import threading
import random
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR

from . import config
from .protocol import status_codes
from .responses import make_body, date_time
from .handler import mythread, logs, logs_compression
from .etag import load_etags


def parse_args():
    parser = argparse.ArgumentParser(description="Multithreaded HTTP server")
    parser.add_argument("port", type=int)
    parser.add_argument("level", type=int, choices=[0, 1, 2])
    return parser.parse_args()


def _request_shutdown(signum, frame):
    raise KeyboardInterrupt


def main():
    args = parse_args()
    config.port = args.port

    os.makedirs(config.VAR_DIR, exist_ok=True)
    logs_compression(config.LOG_FILES[0])
    logs_compression(config.LOG_FILES[1])
    logs_compression(config.LOG_FILES[2])
    logs(args.level)
    load_etags()

    signal.signal(signal.SIGINT, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    server = socket(AF_INET, SOCK_STREAM)
    # Allow immediate rebind after restart instead of waiting out TIME_WAIT.
    server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    server.bind(("", config.port))
    server.listen(5)
    # Bounded accept() so a pending SIGINT/SIGBREAK is delivered promptly even
    # when idle (a blocking accept() is not interruptible by signals on Windows).
    server.settimeout(1)
    print(f"Address : http://{config.ip}:{config.port}")

    try:
        while True:
            try:
                conn, addr = server.accept()
            except TimeoutError:
                continue
            print(f"Connected by {addr}")

            if threading.active_count() < config.MAX_REQUESTS:
                th = threading.Thread(target=mythread, args=(conn,), daemon=True)
                th.start()

            else:
                status_code = 503
                t = random.randint(50, 200)

                body = make_body(status_code)
                msg = f"HTTP/1.1 {status_code} {status_codes[status_code]}\r\n"
                msg += "Date: " + date_time() + "\r\n"
                msg += "Retry-After: " + str(t) + "\r\n"
                msg += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
                msg += "Server: Apache/2.4.46 (Ubuntu) \r\n"
                msg += "Content-Length: " + str(len(body)) + "\r\n"
                msg += "Connection: Close\r\n"
                msg += "Content-Type: text/html; charset=utf-8\r\n\r\n"

                conn.sendall(msg.encode())
                conn.sendall(body)

                conn.close()

    except KeyboardInterrupt:
        print("server stopped")
    finally:
        server.close()


if __name__ == "__main__":
    main()
