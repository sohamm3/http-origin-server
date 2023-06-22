from socket import socket, AF_INET, SOCK_STREAM
import sys
import threading
import os
import stat
import gzip

ip = "127.0.0.1"
port = int(sys.argv[1])

# Locally-created fixtures must live under the server's document root (www/),
# since the server resolves served paths against ROOT, not the test's CWD.
WWW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "www")


def get():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /test.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    data = client.recv(8192)
    print("\nGet Request:\n")
    print(response.decode())
    print(data.decode())
    client.close()


def head():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "HEAD /sample.pdf HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nHead Request:\n")
    print(response.decode())
    client.close()


def delete():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "DELETE /fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n"
    msg += "Authorization: Basic c29oYW06U29oYW1AMjAyMA==\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nDelete Request:\n")
    print(response.decode())
    client.close()


def unauthorized():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "DELETE /fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n"
    msg += "Authorization: Basic c29oYW06d3JvbmdwYXNz\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nDelete Request(unauthorized):\n")
    print(response.decode())
    client.close()


def put():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "PUT /fun.txt HTTP/1.1\r\n"
    msg += "Content-Length: 12\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    msg += "hello world!"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nPut Request:\n")
    print(response.decode())
    client.close()


def post():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "POST /fun.txt HTTP/1.1\r\n"
    msg += "Content-Length: 12\r\n"
    msg += "Content-Type: text/plain\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    msg += "hello world!"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nPost Request:\n")
    print(response.decode())
    client.close()


def method_not_implemented():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "COPY /fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(method not allowed):\n")
    print(response.decode())
    client.close()


def uri_too_long():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /data/files/newfiles/oldfiles/myfiles/datafiles/allfiles/fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(uri too long):\n")
    print(response.decode())
    client.close()


def unsupported():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /file.pp HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(unsupported media type):\n")
    print(response.decode())
    client.close()


def length_required():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "PUT /fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    msg += "hello world!"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nPut Request(length required):\n")
    print(response.decode())
    client.close()


def forbidden():
    # After the W_OK-on-GET fix, GET on a read-only file succeeds (see
    # get_readonly). Write methods still require W_OK: DELETE on the read-only
    # fun.txt (main() sets it read-only first) must return 403 and that
    # permission check happens before auth, so even valid credentials get 403.
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "DELETE /fun.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n"
    msg += "Authorization: Basic c29oYW06U29oYW1AMjAyMA==\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nDelete Request(forbidden - read-only file):\n")
    print(response.decode())
    assert " 403 " in response.decode(), (
        "DELETE on a read-only file did not return 403!"
    )
    client.close()


def version_not_supported():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /file.txt HTTP/2.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(version not supported):\n")
    print(response.decode())
    client.close()


def non_persistent():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "HEAD /http.txt HTTP/1.0\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nHEAD Request(non persistent):\n")
    print(response.decode())
    client.close()


def get_readonly():
    # Regression (W_OK-on-GET bug): GET on a readable but non-writable file must
    # return 200. The server previously wrongly required write access for GET.
    fn = "readonly_test.txt"
    path = os.path.join(WWW, fn)
    with open(path, "w") as f:
        f.write("read only content")
    os.chmod(path, stat.S_IREAD)
    try:
        client = socket(AF_INET, SOCK_STREAM)
        client.connect((ip, port))
        msg = "GET /readonly_test.txt HTTP/1.1\r\n"
        msg += "User-Agent: testing agent\r\n\r\n"
        client.send(msg.encode())
        response = client.recv(1024)
        try:
            client.recv(8192)  # drain body to avoid a server-side reset on close
        except Exception:
            pass
        print("\nGet Request(read-only file -> should be 200):\n")
        print(response.decode())
        assert " 200 " in response.decode(), (
            "GET on a read-only file did not return 200!"
        )
        client.close()
    finally:
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def post_inaccessible():
    # Regression (POST missing-else hang): POST to an existing, non-writable file
    # must return 403 and respond promptly (not hang the worker / client).
    fn = "noperm_test.txt"
    path = os.path.join(WWW, fn)
    with open(path, "w") as f:
        f.write("x")
    os.chmod(path, stat.S_IREAD)
    try:
        client = socket(AF_INET, SOCK_STREAM)
        client.settimeout(10)  # a regressed hang fails here instead of blocking forever
        client.connect((ip, port))
        msg = "POST /noperm_test.txt HTTP/1.1\r\n"
        msg += "Content-Length: 5\r\n"
        msg += "Content-Type: text/plain\r\n"
        msg += "User-Agent: testing agent\r\n\r\n"
        msg += "hello"
        client.send(msg.encode())
        response = client.recv(1024)
        print("\nPost Request(inaccessible file -> should be 403, no hang):\n")
        print(response.decode())
        assert " 403 " in response.decode(), (
            "POST to an inaccessible file did not return 403!"
        )
        client.close()
    finally:
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def malformed_no_terminator():
    # Regression (malformed request handling): a request with no blank-line
    # terminator must still get a response (previously raised ValueError ->
    # dead worker thread -> client hang).
    client = socket(AF_INET, SOCK_STREAM)
    client.settimeout(10)
    client.connect((ip, port))
    msg = "GET /test.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n"  # note: no terminating blank line
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(no header terminator -> should still respond):\n")
    print(response.decode())
    assert "HTTP/" in response.decode(), (
        "malformed request (no terminator) got no response!"
    )
    client.close()


def missing_auth():
    # DELETE without an Authorization header must return 401 (not crash / not 400).
    # Targets test.txt; auth fails so the file is never deleted.
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "DELETE /test.txt HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nDelete Request(missing auth header):\n")
    print(response.decode())
    assert " 401 " in response.decode(), (
        "missing Authorization header did not yield 401!"
    )
    client.close()


def no_user_agent():
    # A request without a User-Agent header must not crash the worker thread.
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /test.txt HTTP/1.1\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    try:
        client.recv(8192)  # drain body to avoid a server-side reset on close
    except Exception:
        pass
    print("\nGet Request(no User-Agent):\n")
    print(response.decode())
    assert " 200 " in response.decode(), "request without User-Agent did not succeed!"
    client.close()


def concurrent_writes():
    # Concurrency test for C1: fire N simultaneous GETs to N *new* files. Each
    # request appends a row to etag.csv (read-modify-append) AND a line to
    # cookies.txt (Set-Cookie). Without the write_lock these interleave and can
    # corrupt etag.csv (causing 500s on later pandas reads) or merge cookie
    # lines. With the lock, every request returns 200 and etag.csv stays well
    # formed with all N new resources present.
    import csv as _csv

    N = 10
    fnames = [f"conc_{i}.txt" for i in range(N)]
    etag_csv = os.path.join(os.path.dirname(WWW), "var", "etag.csv")
    for fn in fnames:
        with open(os.path.join(WWW, fn), "w") as f:
            f.write("concurrent data")
    statuses = {}

    def hit(fn):
        try:
            c = socket(AF_INET, SOCK_STREAM)
            c.settimeout(15)
            c.connect((ip, port))
            c.send(
                (f"GET /{fn} HTTP/1.1\r\nUser-Agent: testing agent\r\n\r\n").encode()
            )
            resp = c.recv(1024).decode(errors="replace")
            statuses[fn] = resp.split("\r\n")[0]
            try:
                c.recv(8192)
            except Exception:
                pass
            c.close()
        except Exception as e:
            statuses[fn] = f"ERROR: {e}"

    threads = [threading.Thread(target=hit, args=(fn,)) for fn in fnames]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    try:
        non200 = {fn: s for fn, s in statuses.items() if " 200 " not in s}
        with open(etag_csv, newline="") as f:
            rows = list(_csv.reader(f))
        malformed = [r for r in rows if r and len(r) != 3]
        present = {r[1] for r in rows if len(r) == 3}
        missing = [fn for fn in fnames if fn not in present]
        print("\nConcurrent writes (C1):")
        print(f"  responses: {len(statuses)}, non-200: {len(non200)}")
        print(
            f"  etag.csv rows: {len(rows)}, malformed: {len(malformed)}, missing resources: {len(missing)}"
        )
        assert not non200, f"concurrent requests returned non-200: {non200}"
        assert not malformed, (
            f"etag.csv has {len(malformed)} malformed rows after concurrent writes!"
        )
        assert not missing, f"etag.csv missing rows for concurrent files: {missing}"
    finally:
        for fn in fnames:
            p = os.path.join(WWW, fn)
            if os.path.exists(p):
                os.remove(p)


def path_traversal():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /../../../../etc/passwd HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024)
    print("\nGet Request(path traversal blocked):\n")
    print(response.decode())
    assert " 403 " in response.decode(), "path traversal was NOT blocked!"
    client.close()


def _hval(head, name):
    for line in head.split("\r\n"):
        if line.lower().startswith(name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


def _fetch(method, path, inm=None, accept_encoding=None):
    c = socket(AF_INET, SOCK_STREAM)
    c.settimeout(8)
    c.connect((ip, port))
    req = f"{method} {path} HTTP/1.1\r\nUser-Agent: testing agent\r\n"
    if inm is not None:
        req += f"If-None-Match: {inm}\r\n"
    if accept_encoding is not None:
        req += f"Accept-Encoding: {accept_encoding}\r\n"
    req += "\r\n"
    c.send(req.encode())
    raw = b""
    head = ""
    body = b""
    try:
        while b"\r\n\r\n" not in raw:
            chunk = c.recv(4096)
            if not chunk:
                break
            raw += chunk
        head_b, _, body = raw.partition(b"\r\n\r\n")
        head = head_b.decode(errors="replace")
        status = head.split("\r\n")[0]
        cl = _hval(head, "Content-Length")
        clen = int(cl) if cl is not None else 0
        if method != "HEAD" and " 304 " not in status:
            while len(body) < clen:
                chunk = c.recv(4096)
                if not chunk:
                    break
                body += chunk
    except (TimeoutError, ValueError):
        pass
    c.close()
    status = head.split("\r\n")[0] if head else ""
    return status, head, body


def conditional_get():
    s0, h0, _ = _fetch("GET", "/test.txt")
    etag = _hval(h0, "ETag")
    print("\nConditional GET: learned ETag =", etag, "| initial:", s0)
    assert " 200 " in s0 and etag, f"could not learn ETag (status={s0}, etag={etag})"

    s1, _, b1 = _fetch("GET", "/test.txt", inm=etag)
    assert " 304 " in s1, f"matching If-None-Match did not yield 304: {s1}"
    assert b1 == b"", "304 response must have no body!"

    s2, _, b2 = _fetch("GET", "/test.txt", inm='"does-not-match"')
    assert " 200 " in s2, f"non-matching If-None-Match did not yield 200: {s2}"
    assert b2 != b"", "200 response should include a body!"

    s3, _, b3 = _fetch("HEAD", "/test.txt", inm=etag)
    assert " 304 " in s3, f"HEAD matching If-None-Match did not yield 304: {s3}"
    assert b3 == b"", "HEAD 304 must have no body!"

    s4, _, b4 = _fetch("HEAD", "/test.txt", inm='"nope"')
    assert " 200 " in s4, f"HEAD non-matching did not yield 200: {s4}"
    assert b4 == b"", "HEAD 200 must have no body!"
    print("conditional_get OK")


def conditional_new_resource():
    fn = "cond_new.txt"
    path = os.path.join(WWW, fn)
    with open(path, "w") as f:
        f.write("freshly created")
    try:
        s0, h0, _ = _fetch("GET", "/cond_new.txt")
        etag = _hval(h0, "ETag")
        print("\nConditional GET (new resource): initial", s0, "etag", etag)
        assert " 200 " in s0 and etag, (
            f"new resource GET failed (status={s0}, etag={etag})"
        )
        s1, _, b1 = _fetch("GET", "/cond_new.txt", inm=etag)
        assert " 304 " in s1, (
            f"new-resource matching If-None-Match did not yield 304: {s1}"
        )
        assert b1 == b"", "304 must have no body!"
    finally:
        os.remove(path)


def gzip_compression():
    s1, h1, b1 = _fetch("GET", "/test.txt", accept_encoding="gzip, deflate")
    assert " 200 " in s1, f"gzip GET not 200: {s1}"
    assert _hval(h1, "Content-Encoding") == "gzip", "missing Content-Encoding: gzip!"
    assert int(_hval(h1, "Content-Length")) == len(b1), (
        "Content-Length != compressed body length!"
    )

    s2, h2, b2 = _fetch("GET", "/test.txt", accept_encoding="identity")
    assert " 200 " in s2, f"identity GET not 200: {s2}"
    assert _hval(h2, "Content-Encoding") is None, (
        "unexpected Content-Encoding when gzip not accepted!"
    )

    assert gzip.decompress(b1) == b2, (
        "gzip body does not decompress to the uncompressed body!"
    )

    s3, h3, b3 = _fetch("HEAD", "/test.txt", accept_encoding="gzip")
    assert " 200 " in s3, f"HEAD gzip not 200: {s3}"
    assert _hval(h3, "Content-Encoding") == "gzip", (
        "HEAD missing Content-Encoding: gzip!"
    )
    assert _hval(h3, "Content-Length") == _hval(h1, "Content-Length"), (
        "HEAD Content-Length != GET compressed length!"
    )
    assert b3 == b"", "HEAD must have no body!"
    print("gzip_compression OK")


def gzip_304_unaffected():
    s0, h0, _ = _fetch("GET", "/test.txt", accept_encoding="gzip")
    etag = _hval(h0, "ETag")
    s1, h1, b1 = _fetch("GET", "/test.txt", inm=etag, accept_encoding="gzip")
    assert " 304 " in s1, f"conditional + gzip did not yield 304: {s1}"
    assert _hval(h1, "Content-Encoding") is None, "304 must not carry Content-Encoding!"
    assert b1 == b"", "304 must have no body!"
    print("gzip_304_unaffected OK")


def gzip_binary_uncompressed():
    s, h, b = _fetch("GET", "/img.png", accept_encoding="gzip")
    assert " 200 " in s, f"binary GET not 200: {s}"
    assert _hval(h, "Content-Encoding") is None, (
        "binary asset must not be gzip-compressed!"
    )
    assert int(_hval(h, "Content-Length")) == len(b), (
        "binary Content-Length != body length!"
    )
    print("gzip_binary_uncompressed OK")


def large_file_streaming():
    fn = "large_stream.pdf"
    path = os.path.join(WWW, fn)
    data = b"PDFDATA-" * 150000
    with open(path, "wb") as f:
        f.write(data)
    try:
        s, h, b = _fetch("GET", "/large_stream.pdf")
        assert " 200 " in s, f"large GET not 200: {s}"
        assert _hval(h, "Content-Encoding") is None, (
            "non-compressible large file must not be gzipped!"
        )
        assert int(_hval(h, "Content-Length")) == len(data), (
            "Content-Length != file size!"
        )
        assert b == data, "streamed body does not match file content!"

        sh, hh, bh = _fetch("HEAD", "/large_stream.pdf")
        assert " 200 " in sh, f"large HEAD not 200: {sh}"
        assert int(_hval(hh, "Content-Length")) == len(data), (
            "HEAD Content-Length != file size!"
        )
        assert bh == b"", "HEAD must have no body!"

        sg, hg, bg = _fetch("GET", "/large_stream.pdf", accept_encoding="gzip")
        assert _hval(hg, "Content-Encoding") is None, (
            "binary file gzipped despite non-compressible type!"
        )
        assert bg == data, "gzip-accepted binary stream body mismatch!"

        s0, h0, _ = _fetch("GET", "/large_stream.pdf")
        etag = _hval(h0, "ETag")
        s1, _, b1 = _fetch("GET", "/large_stream.pdf", inm=etag)
        assert " 304 " in s1, "conditional GET on streamed resource did not yield 304!"
        assert b1 == b"", "304 on streamed resource must have no body!"
        print("large_file_streaming OK")
    finally:
        os.remove(path)


def large_text_gzip():
    fn = "large_text.txt"
    path = os.path.join(WWW, fn)
    data = ("hello world line\n" * 50000).encode()
    with open(path, "wb") as f:
        f.write(data)
    try:
        s, h, b = _fetch("GET", "/large_text.txt", accept_encoding="gzip")
        assert " 200 " in s, f"large text GET not 200: {s}"
        assert _hval(h, "Content-Encoding") == "gzip", (
            "large compressible text not gzipped!"
        )
        assert int(_hval(h, "Content-Length")) == len(b), (
            "Content-Length != compressed body length!"
        )
        assert gzip.decompress(b) == data, "decompressed large text mismatch!"
        print("large_text_gzip OK")
    finally:
        os.remove(path)


def moved_permanently():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /old.html HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024).decode(errors="replace")
    print("\nGet Request(moved permanently):\n")
    print(response)
    assert " 301 " in response, "GET /old.html did not return 301!"
    assert "Location: /new.html" in response, (
        "301 response missing Location: /new.html!"
    )
    client.close()


def redirect_target_direct():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "GET /new.html HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    response = client.recv(1024).decode(errors="replace")
    try:
        client.recv(8192)
    except Exception:
        pass
    print("\nGet Request(redirect target direct -> should be 200):\n")
    print(response)
    assert " 200 " in response, (
        "GET /new.html (the redirect target) did not return 200!"
    )
    client.close()


def head_redirect():
    client = socket(AF_INET, SOCK_STREAM)
    client.connect((ip, port))
    msg = "HEAD /old.html HTTP/1.1\r\n"
    msg += "User-Agent: testing agent\r\n\r\n"
    client.send(msg.encode())
    raw = client.recv(2048).decode(errors="replace")
    print("\nHead Request(moved permanently):\n")
    print(raw)
    assert " 301 " in raw, "HEAD /old.html did not return 301!"
    assert "Location: /new.html" in raw, (
        "HEAD 301 response missing Location: /new.html!"
    )
    head, _, after = raw.partition("\r\n\r\n")
    assert after == "", "HEAD redirect response must not have a body!"
    client.close()


def head_matches_get():
    # HTTP/1.0 so the server closes the connection after responding; this lets
    # the client read to EOF and observe exactly whether a body was sent.
    def fetch(method):
        c = socket(AF_INET, SOCK_STREAM)
        c.settimeout(8)
        c.connect((ip, port))
        c.send(
            (
                f"{method} /test.txt HTTP/1.0\r\nUser-Agent: testing agent\r\n\r\n"
            ).encode()
        )
        raw = b""
        try:
            while True:
                chunk = c.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except TimeoutError:
            pass
        c.close()
        head, _, after = raw.partition(b"\r\n\r\n")
        return head.decode(errors="replace"), after

    get_head, get_body = fetch("GET")
    head_head, head_body = fetch("HEAD")

    def clen(h):
        for line in h.split("\r\n"):
            if line.lower().startswith("content-length:"):
                return line.split(":", 1)[1].strip()
        return None

    print("\nHEAD vs GET correctness:")
    print(
        "  GET Content-Length:",
        clen(get_head),
        "| HEAD Content-Length:",
        clen(head_head),
    )
    assert " 200 " in head_head, "HEAD /test.txt did not return 200!"
    assert head_body == b"", "HEAD response must have no body!"
    assert clen(head_head) is not None, "HEAD response missing Content-Length!"
    assert clen(head_head) == clen(get_head), "HEAD Content-Length must equal GET's!"


def main():
    get_thread = threading.Thread(target=get)
    get_thread.start()
    get_thread.join()

    head_thread = threading.Thread(target=head)
    head_thread.start()
    head_thread.join()

    put_thread = threading.Thread(target=put)
    put_thread.start()
    put_thread.join()

    delete_thread = threading.Thread(target=delete)
    delete_thread.start()
    delete_thread.join()

    post_thread = threading.Thread(target=post)
    post_thread.start()
    post_thread.join()

    unauthorized_thread = threading.Thread(target=unauthorized)
    unauthorized_thread.start()
    unauthorized_thread.join()

    method_thread = threading.Thread(target=method_not_implemented)
    method_thread.start()
    method_thread.join()

    uri_thread = threading.Thread(target=uri_too_long)
    uri_thread.start()
    uri_thread.join()

    unsupported_thread = threading.Thread(target=unsupported)
    unsupported_thread.start()
    unsupported_thread.join()

    length_required_thread = threading.Thread(target=length_required)
    length_required_thread.start()
    length_required_thread.join()

    put_thread = threading.Thread(target=put)
    put_thread.start()
    put_thread.join()

    os.chmod(os.path.join(WWW, "fun.txt"), 0o000)

    forbidden_thread = threading.Thread(target=forbidden)
    forbidden_thread.start()
    forbidden_thread.join()

    version_not_supported_thread = threading.Thread(target=version_not_supported)
    version_not_supported_thread.start()
    version_not_supported_thread.join()

    non_persistent_thread = threading.Thread(target=non_persistent)
    non_persistent_thread.start()
    non_persistent_thread.join()

    moved_permanently_thread = threading.Thread(target=moved_permanently)
    moved_permanently_thread.start()
    moved_permanently_thread.join()

    redirect_target_direct_thread = threading.Thread(target=redirect_target_direct)
    redirect_target_direct_thread.start()
    redirect_target_direct_thread.join()

    head_redirect_thread = threading.Thread(target=head_redirect)
    head_redirect_thread.start()
    head_redirect_thread.join()

    head_matches_get_thread = threading.Thread(target=head_matches_get)
    head_matches_get_thread.start()
    head_matches_get_thread.join()

    conditional_get_thread = threading.Thread(target=conditional_get)
    conditional_get_thread.start()
    conditional_get_thread.join()

    conditional_new_resource_thread = threading.Thread(target=conditional_new_resource)
    conditional_new_resource_thread.start()
    conditional_new_resource_thread.join()

    gzip_compression_thread = threading.Thread(target=gzip_compression)
    gzip_compression_thread.start()
    gzip_compression_thread.join()

    gzip_304_unaffected_thread = threading.Thread(target=gzip_304_unaffected)
    gzip_304_unaffected_thread.start()
    gzip_304_unaffected_thread.join()

    gzip_binary_uncompressed_thread = threading.Thread(target=gzip_binary_uncompressed)
    gzip_binary_uncompressed_thread.start()
    gzip_binary_uncompressed_thread.join()

    large_file_streaming_thread = threading.Thread(target=large_file_streaming)
    large_file_streaming_thread.start()
    large_file_streaming_thread.join()

    large_text_gzip_thread = threading.Thread(target=large_text_gzip)
    large_text_gzip_thread.start()
    large_text_gzip_thread.join()

    path_traversal_thread = threading.Thread(target=path_traversal)
    path_traversal_thread.start()
    path_traversal_thread.join()

    missing_auth_thread = threading.Thread(target=missing_auth)
    missing_auth_thread.start()
    missing_auth_thread.join()

    no_user_agent_thread = threading.Thread(target=no_user_agent)
    no_user_agent_thread.start()
    no_user_agent_thread.join()

    get_readonly_thread = threading.Thread(target=get_readonly)
    get_readonly_thread.start()
    get_readonly_thread.join()

    post_inaccessible_thread = threading.Thread(target=post_inaccessible)
    post_inaccessible_thread.start()
    post_inaccessible_thread.join()

    malformed_no_terminator_thread = threading.Thread(target=malformed_no_terminator)
    malformed_no_terminator_thread.start()
    malformed_no_terminator_thread.join()

    # C1: concurrency test runs its own internal thread fan-out (not joined here
    # one-at-a-time like the others).
    concurrent_writes()


if __name__ == "__main__":
    main()
