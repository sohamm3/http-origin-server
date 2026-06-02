# Raw-Socket HTTP/1.0–1.1 Server

A multithreaded HTTP/1.0–1.1 origin server implemented over raw TCP sockets in Python with no web framework, no `http.server`, and no third-party libraries.

## Architecture overview

The request path moves through the package modules listed in the table below. A connection is accepted on the main thread, handed to a worker thread for its entire lifetime, parsed by hand, dispatched by method, and serialized back to the client. The worker thread is created at `accept()` and ends after one request.

```text
   Client TCP connection
        |
        v
   httpserver/server.py : main()
     accept() loop  (server socket has a 1s timeout so SIGINT/SIGBREAK is seen when idle)
        |
        |-- threading.active_count() >= MAX_REQUESTS ----> 503 + Retry-After, conn.close()
        |
        v   (under the cap)
   threading.Thread(target=mythread, daemon=True)   <--- worker thread STARTS here
        |
        v
   httpserver/handler.py : mythread(conn)
     conn.setblocking(0); non-blocking recv loop accumulates bytes until ~2s idle
     split once on b"\r\n\r\n"  ->  (headers_text, body)
     conn.setblocking(True)
        |
        v
   httpserver/handler.py : helper(headers_text, body, conn)
        |
        |-- split_data()  : parse request line + headers (method, version, path, etc.)
        |
        |-- guard chain (first match wins):
        |     len(uri) > MAX_URI            -> 414
        |     method not in Allow           -> 405 (+ Allow header)
        |     version not in http_versions  -> 505
        |     not is_safe_path(path)         -> 403   (realpath containment, fileio.py)
        |     path in redirects             -> 301 (+ Location)
        |     path in no  ("" / favicon.ico) -> literal b"hello"
        |
        |-- method dispatch: GET | HEAD | PUT | POST | DELETE
        |     builds the response with httpserver/responses.py
        |     reads/streams/writes files with httpserver/fileio.py
        |     validates ETag / Last-Modified with httpserver/etag.py
        |
        v
   conn.sendall(headers)  then  body or stream_file() chunks
        |
        |-- method branches return here; the socket is closed when the worker
        |   thread ends and the connection is garbage-collected (both HTTP/1.0
        |   and HTTP/1.1 take this path)
        |-- the trailing `if version == "HTTP/1.0": socket.close()` is reached only
        |   by the fall-through guard responses (414/405/505/403/301/"no"), which
        |   do not return
        v
   worker thread ENDS  (one request per connection; no second-request read loop)
```

| **Module**                | **Responsibility**                                                                                                                                                                  |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `httpserver/server.py`    | `accept()` loop, worker-thread spawn, 503 admission path, signal handlers, startup (log rotation, ETag load)                                                                        |
| `httpserver/handler.py`   | Request parsing, guard chain, method dispatch, all per-method logic, the worker `mythread()`, logging setup/rotation                                                                |
| `httpserver/responses.py` | Header/response string builders (`get_headers`, `put_post`, `ok`, `delete_header`, `allow_header`, `redirect_header`, `not_modified_header`, `error`, `make_body`), cookie issuance |
| `httpserver/fileio.py`    | Path resolution, file read/write, chunked streaming, MIME detection, traversal check, compression eligibility                                                                       |
| `httpserver/etag.py`      | In-memory ETag store loaded from `var/etag.csv`; ETag derivation                                                                                                                    |
| `httpserver/protocol.py`  | Status-code, status-message, MIME, HTTP-version, binary-extension, and `Allow` tables                                                                                               |
| `httpserver/config.py`    | Tunables and on-disk paths                                                                                                                                                          |
| `httpserver/locks.py`     | The single shared `threading.Lock`                                                                                                                                                  |

## Directory structure

```text
.
|- server.py            # root shim: imports httpserver.server.main and runs it (entry point only)
|- httpserver/          # Python package - all server source
|    |- __init__.py
|    |- server.py       # accept loop, thread spawn, 503 path, signals, startup
|    |- handler.py      # parsing, guard chain, dispatch, per-method logic, worker, logging
|    |- responses.py    # header/response builders, cookie issuance
|    |- fileio.py       # file read/write/stream, MIME detection, path resolution, traversal check
|    |- etag.py         # in-memory ETag store + ETag derivation
|    |- protocol.py     # status/MIME/version/Allow data tables
|    |- config.py       # tunables and paths
|    |- locks.py        # shared threading.Lock
|- www/                 # document root - only these files are served
|- var/                 # runtime data: etag.csv, cookies.txt, *.log  (gitignored)
|- tests/               # client_tests.py, browser_open.py, run_all.py, CASES.md
|- scripts/             # init_etag.py (ETag store init), scratch_inspect.py (ad-hoc probe)
```

`var/` is excluded from version control (`.gitignore`) and is created at startup with `os.makedirs(VAR_DIR, exist_ok=True)` if absent. Served content lives in `www/`; the server resolves every requested path against that directory and never serves files from the project root.

## Prerequisites and setup

Python 3 with the standard library only. There are no third-party dependencies. An earlier version read `etag.csv` with `pandas` on every request; `httpserver/etag.py` now loads the file once into a dict with the `csv` module, so `pandas` is no longer imported or required.

DELETE authentication credentials are read from environment variables in `httpserver/config.py`:

```bash
export HTTP_AUTH_USER=youruser
export HTTP_AUTH_PASS=yourpass
```

If these variables are unset, `config.py` falls back to the hardcoded defaults when the variables are unset. DELETE therefore authenticates against those defaults when the environment is not set - it does not reject everything. Set the variables to use your own credentials. (Credentials travel as base64 Basic auth over plaintext)

Initialize the ETag store before the first run:

```bash
python scripts/init_etag.py
```

This globs every file under `www/` and writes `var/etag.csv` with one row per file (`E-Tag, resource, last modified`). The server also tolerates a missing store: `etag.py: load_etags()` creates `var/etag.csv` with a header row if it does not exist.

## Running the server

The entry point is the root `server.py` shim, which calls `httpserver.server.main()`.

```bash
python server.py <port> <log_level>
```

```bash
python server.py 8080 0
# prints: Address : http://127.0.0.1:8080
```

`<log_level>` selects which file receives log records:

| **Level** | **File**            | **Python level** |
| --------- | ------------------- | ---------------- |
| 0         | `var/user.log`      | INFO             |
| 1         | `var/debug.log`     | DEBUG            |
| 2         | `var/developer.log` | WARNING          |

Running the request harness (two terminals):

```bash
# Terminal 1
python server.py 8080 0

# Terminal 2
python tests/client_tests.py 8080
```

`tests/client_tests.py` sends requests and prints responses; its early method checks print without asserting, while later checks (conditional GET, gzip, streaming, traversal, auth, concurrency) do assert. `tests/run_all.py 8080` runs the same checks but first calls `tests/browser_open.py`, which opens roughly a dozen browser tabs through the `webbrowser` module - run it only if that side effect is wanted. Neither is a complete automated test suite. `tests/CASES.md` documents the expected input/output for every behavior.

## Implemented features

### Multithreaded raw-socket serving

Each accepted TCP connection is served on its own thread, with no framework between the socket and the response bytes.
The main loop calls `socket.accept()` and starts a daemon `threading.Thread` per connection; the worker reads, dispatches, responds, and exits.
Implementation: `httpserver/server.py: main()`, `httpserver/handler.py: mythread()`

```bash
# Two requests at once are handled by two separate threads.
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/test.txt &
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/sample.json &
wait
# Expected: 200 and 200 (printed in either order)
```

### GET static file

Returns the contents of a file under `www/` with metadata headers.
`helper()` confirms the file exists, is readable, and has a whitelisted MIME type, then sends headers followed by the body (streamed or gzip-compressed depending on type and `Accept-Encoding`).
Implementation: `httpserver/handler.py: helper()`, `httpserver/responses.py: get_headers()`

```bash
curl -si http://localhost:8080/test.txt
# Expected: HTTP/1.1 200 OK
#           Content-Type: text/plain
#           Content-Length: <size>, ETag: "<mtime>-<size>", Last-Modified: <date>
```

### HEAD

Returns the same status line and headers a GET would produce, with no message body.
The HEAD branch builds the identical header block (including the `Content-Length` GET would send - the compressed length when gzip is negotiated) and skips the `sendall` of the body.
Implementation: `httpserver/handler.py: helper()`, `httpserver/responses.py: get_headers()`

```bash
curl -si -X HEAD http://localhost:8080/test.txt
# Expected: HTTP/1.1 200 OK, Content-Length: <size>, no body bytes
```

### PUT (create and overwrite)

Writes the request body to the named path under `www/`, returning 201 for a new file and 200 for an overwrite.
`helper()` requires a `Content-Length`, checks the body against `MAX_PAYLOAD`, then calls `write_file()`; a missing target yields 201 via `put_post()`, an existing writable target yields 200 via `ok()`.
Implementation: `httpserver/handler.py: helper()`, `httpserver/fileio.py: write_file()`, `httpserver/responses.py: put_post()` / `ok()`

```bash
curl -si -X PUT http://localhost:8080/put_test.txt \
  -H "Content-Length: 13" --data "hello put one"
# Expected: HTTP/1.1 201 Created, Location: <abs path under www/>

curl -si -X PUT http://localhost:8080/put_test.txt \
  -H "Content-Length: 15" --data "hello overwrite"
# Expected: HTTP/1.1 200 OK
```

### POST (new file and collision naming)

Writes the request body; when the target already exists it writes a new file with a parenthesized index instead of overwriting.
For an existing path, `post_name()` globs the directory for matching names and returns `name(N).ext`, which `write_file()` then creates.
Implementation: `httpserver/handler.py: helper()`, `httpserver/fileio.py: post_name()` / `write_file()`

```bash
curl -si -X POST http://localhost:8080/post_test.txt \
  -H "Content-Length: 14" --data "hello post one"
# Expected: HTTP/1.1 201 Created (creates www/post_test.txt)

curl -si -X POST http://localhost:8080/post_test.txt \
  -H "Content-Length: 9" --data "collision"
# Expected: HTTP/1.1 201 Created (creates www/post_test(1).txt; original unchanged)
```

### DELETE with HTTP Basic authentication

Removes a file under `www/` only when valid Basic credentials are supplied.
`auth()` extracts the base64 credential, decodes it, splits on the first `:`, and compares username and password with `hmac.compare_digest` (a length-independent comparison); the permission check on the target runs before authentication, so an unwritable file is rejected first.
Implementation: `httpserver/handler.py: helper()` / `auth()`, `httpserver/responses.py: delete_header()`

```bash
CRED=$(printf '%s:%s' "$HTTP_AUTH_USER" "$HTTP_AUTH_PASS" | base64)
curl -si -X DELETE http://localhost:8080/put_test.txt \
  -H "Authorization: Basic $CRED"
# Expected: HTTP/1.1 200 OK (file removed from www/)
# Encode your credentials: printf '%s:%s' "$HTTP_AUTH_USER" "$HTTP_AUTH_PASS" | base64
```

### Method enforcement (405 + Allow)

Rejects any method outside the supported five and advertises what is allowed.
The guard `method not in Allow` (from `protocol.py`) returns 405 with an `Allow` header listing the five methods.
Implementation: `httpserver/handler.py: helper()`, `httpserver/responses.py: allow_header()`, `httpserver/protocol.py: Allow`

```bash
curl -si -X PATCH http://localhost:8080/test.txt
# Expected: HTTP/1.1 405 Method Not Allowed
#           Allow: GET, HEAD, DELETE, PUT, POST
```

### Request-validation guards (411 / 413 / 414)

Rejects requests with no `Content-Length` on a write, an oversized body, or an over-long URI.
`helper()` returns 411 when `Content-Length` is absent on PUT/POST, 413 when the received body length is not below `MAX_PAYLOAD`, and 414 when the request-target length exceeds `MAX_URI`.
Implementation: `httpserver/handler.py: helper()`, `httpserver/config.py: MAX_PAYLOAD` / `MAX_URI`

```bash
# 414: URI longer than MAX_URI (50)
curl -si "http://localhost:8080/$(python -c "print('a'*60)")"
# Expected: HTTP/1.1 414 URI Too Long

# 413: body at/over MAX_PAYLOAD (512000)
python -c "print('x'*600000)" | curl -si -X PUT \
  http://localhost:8080/big.txt -H "Content-Length: 600001" --data-binary @-
# Expected: HTTP/1.1 413 Payload Too Large
```

```bash
# 411: PUT with no Content-Length. curl --data always adds Content-Length,
# so a raw socket is needed to omit it:
python -c "import socket,time; s=socket.socket(); s.connect(('127.0.0.1',8080)); \
s.send(b'PUT /x.txt HTTP/1.1\r\nUser-Agent: t\r\n\r\nbody'); time.sleep(3); \
print(s.recv(120).decode().splitlines()[0])"
# Expected: HTTP/1.1 411 Length Required
```

### MIME whitelist (415)

Serves only file types on an allow-list; other existing files are refused on read.
`file_type()` maps the name through `mimetypes.guess_type`; if the result is not in `protocol.mime_types`, the GET/HEAD branch returns 415.
Implementation: `httpserver/handler.py: helper()`, `httpserver/fileio.py: file_type()`, `httpserver/protocol.py: mime_types`

```bash
curl -si -X PUT http://localhost:8080/test.exe -H "Content-Length: 4" --data "data"
# Expected: HTTP/1.1 201 Created (PUT does not MIME-check)
curl -si http://localhost:8080/test.exe
# Expected: HTTP/1.1 415 Unsupported Media Type (.exe is not in mime_types)
```

### Conditional caching (304 Not Modified)

On GET/HEAD, returns 304 with no body when the client's validator still matches the file, avoiding the payload transfer.
`if_none_match()` is compared against the current ETag with `etag_matches()` (handling `*`, comma lists, and weak `W/` prefixes); if `If-None-Match` is absent, `if_modified_since()` is compared against the file's `Last-Modified`; `If-None-Match` takes precedence.
Implementation: `httpserver/handler.py: helper()` / `if_none_match()` / `if_modified_since()` / `etag_matches()`, `httpserver/etag.py: get_etag()`

```bash
# Step 1: capture the ETag
curl -si http://localhost:8080/test.txt | grep -i ^ETag
# e.g. ETag: "1780369794-1506"

# Step 2: send it back
curl -si http://localhost:8080/test.txt -H 'If-None-Match: "1780369794-1506"'
# Expected: HTTP/1.1 304 Not Modified, no body

# Last-Modified variant
LMOD=$(curl -si http://localhost:8080/test.txt | grep -i ^Last-Modified | sed 's/^[^:]*: //I' | tr -d '\r')
curl -si http://localhost:8080/test.txt -H "If-Modified-Since: $LMOD"
# Expected: HTTP/1.1 304 Not Modified, no body
```

### gzip response compression

Compresses text-type responses when the client offers gzip.
`should_compress()` returns true when the MIME type is in `compressible_types` and `"gzip"` appears in `Accept-Encoding`; the body is then `gzip.compress`-ed, `Content-Encoding: gzip` is added, and `Content-Length` is set to the compressed size.
Implementation: `httpserver/handler.py: helper()`, `httpserver/fileio.py: should_compress()`, `httpserver/responses.py: get_headers()`

```bash
curl -si http://localhost:8080/test.txt -H "Accept-Encoding: gzip" -o /dev/null -D -
# Expected: HTTP/1.1 200 OK, Content-Encoding: gzip, Content-Length: <compressed size>

curl -si http://localhost:8080/img.png -H "Accept-Encoding: gzip" -o /dev/null -D -
# Expected: HTTP/1.1 200 OK, NO Content-Encoding (image/png is not a compressible type)
```

### Streaming file delivery

Sends a file body in fixed-size chunks rather than reading the whole file into memory.
The uncompressed path sets `Content-Length` from `os.path.getsize` and calls `stream_file()`, which loops `f.read(65536)` / `sock.sendall(chunk)` until EOF.
Implementation: `httpserver/handler.py: helper()`, `httpserver/fileio.py: stream_file()`

```bash
curl -s http://localhost:8080/video.mp4 -o /dev/null -w "status=%{http_code} bytes=%{size_download}\n"
# Expected: status=200 bytes=<exact file size>  (delivered in 64 KiB chunks)
```

### Connection-admission control (503)

Refuses new connections with 503 when the worker-thread count is at the cap.
Before spawning a worker, `main()` checks `threading.active_count() < MAX_REQUESTS`; if not, it writes a 503 with a randomized `Retry-After` and closes the connection.
Implementation: `httpserver/server.py: main()`, `httpserver/config.py: MAX_REQUESTS`

```bash
# With MAX_REQUESTS temporarily lowered (e.g. to 2) and the server restarted:
for i in $(seq 1 5); do curl -s -o /dev/null -w "%{http_code} " http://localhost:8080/test.txt & done; wait; echo
# Expected: a mix such as "200 503 503 503 200", each 503 carrying Retry-After: <50-200>
```

### Path-traversal protection

Refuses any request whose resolved path escapes `www/`.
`is_safe_path()` joins the request path onto `ROOT`, canonicalizes both with `os.path.realpath` (which collapses `..` and follows symlinks), normalizes case, and confirms the target stays within `ROOT` before any file operation runs.
Implementation: `httpserver/fileio.py: is_safe_path()`, `httpserver/handler.py: helper()`

```bash
curl -si "http://localhost:8080/../../etc/passwd"
# Expected: HTTP/1.1 403 or 404 - never the file contents
```

### Shared-state write serialization

Serializes concurrent writes to the runtime data files so threads cannot interleave bytes.
A single module-level `threading.Lock` is held around every append to `var/cookies.txt`, every ETag record write, and every `write_file`/`os.remove` on a served file.
Implementation: `httpserver/locks.py: write_lock`, used in `httpserver/responses.py: write_cookie()`, `httpserver/etag.py: get_etag()`, `httpserver/fileio.py: write_file()`

```bash
# Concurrent first-time GETs each append a cookie line and an ETag row under the lock.
for i in $(seq 1 8); do curl -s -o /dev/null http://localhost:8080/test.txt & done; wait
# Expected: var/cookies.txt and var/etag.csv contain well-formed lines, none merged
```

### Log rotation

Compresses an aged log file at startup and starts a fresh one.
For each stream, `logs_compression()` compares the log file's age to `EXPIRES`; if older, it gzips the file into `var/<stream>logFiles/` and removes the original before `logs()` opens a new file.
Implementation: `httpserver/handler.py: logs_compression()` / `logs()`, `httpserver/config.py: EXPIRES`

```bash
# With EXPIRES temporarily set to 1 and the server restarted twice a few seconds apart:
ls var/userlogFiles/
# Expected: userlogfile1.gz  (the previous var/user.log, compressed)
```

### Shutdown on SIGINT/SIGBREAK

Stops accepting and closes the listening socket on an interrupt signal.
`SIGINT` (and `SIGBREAK` where present) is mapped to a handler that raises `KeyboardInterrupt`; `main()` catches it, prints `server stopped`, and runs `finally: server.close()`. Worker threads are daemon threads, so any request in flight is dropped rather than drained, and `SIGTERM` is not handled (see Known limitations).
Implementation: `httpserver/server.py: main()` / `_request_shutdown()`

```bash
# In the server terminal, press Ctrl+C (or Ctrl+Break on Windows):
# Expected stdout: server stopped   (process exits 0, no traceback)
```

### ETag store and cookie generation

Derives a per-file ETag and persists it, and issues a UUID cookie to clients that arrive without one.
`get_etag()` computes `"<int(mtime)>-<size>"` from `os.stat` (so the value changes when the file changes) and records it once in `var/etag.csv`; `write_cookie()` appends a `uuid.uuid1()` to `var/cookies.txt` and emits `Set-Cookie` only when the request carried no `Cookie` header.
Implementation: `httpserver/etag.py: get_etag()` / `load_etags()`, `httpserver/responses.py: write_cookie()`

```bash
curl -si http://localhost:8080/test.txt | grep -iE "^ETag|^Set-Cookie"
# Expected: ETag: "<mtime>-<size>"
#           Set-Cookie: id=<uuid>; Max-Age=120

curl -si http://localhost:8080/test.txt -H "Cookie: id=anything"
# Expected: HTTP/1.1 200 OK, no Set-Cookie header (cookie is never read back to identify a session)
```

## Configuration reference

Every field in `httpserver/config.py`. Paths are derived from the package location; `ROOT` and `VAR_DIR` are absolute at runtime.

| **Field**      | **Type** | **Default**                                          | **Effect**                                                          |
| -------------- | -------- | ---------------------------------------------------- | ------------------------------------------------------------------- |
| `USERNAME`     | str      | env `HTTP_AUTH_USER`, else hardcoded default         | DELETE auth username                                                |
| `PASSWORD`     | str      | env `HTTP_AUTH_PASS`, else hardcoded default         | DELETE auth password                                                |
| `ROOT`         | str      | `<base>/www`                                         | Document root; all served paths resolve under it                    |
| `VAR_DIR`      | str      | `<base>/var`                                         | Runtime data directory (created at startup)                         |
| `ETAG_CSV`     | str      | `<base>/var/etag.csv`                                | ETag store file                                                     |
| `COOKIES_FILE` | str      | `<base>/var/cookies.txt`                             | Cookie append file                                                  |
| `LOG_FILES`    | dict     | `var/user.log`, `var/debug.log`, `var/developer.log` | Log file per level (0/1/2)                                          |
| `EXPIRES`      | int      | `43200`                                              | Log age in seconds before startup gzip rotation                     |
| `MAX_REQUESTS` | int      | `20`                                                 | Worker-thread cap before a new connection gets 503                  |
| `MAX_URI`      | int      | `50`                                                 | Request-target length above which a request gets 414                |
| `MAX_PAYLOAD`  | int      | `512000`                                             | Body byte count at/above which PUT/POST gets 413                    |
| `MOVED`        | str      | `<base>/www/old.html`                                | Defined; the active redirect mapping is `redirects` in `handler.py` |
| `NEW`          | str      | `<base>/www/new.html`                                | Defined; redirect target reference (active map is in `handler.py`)  |
| `ip`           | str      | `127.0.0.1`                                          | Host string used in emitted headers                                 |
| `port`         | int/None | set from CLI at startup                              | Bind port, assigned in `main()`                                     |

## Example requests and failure simulation

Start the server first: `python server.py 8080 0`.

### Group A: HTTP methods

A create → overwrite → collision → delete lifecycle in one runnable sequence (single GET and HEAD examples are in §6; the DELETE auth-failure cases are in Group D below):

```bash
curl -si -X PUT http://localhost:8080/a.txt -H "Content-Length: 5" --data "hello"
# Expected: HTTP/1.1 201 Created (new file)

curl -si -X PUT http://localhost:8080/a.txt -H "Content-Length: 6" --data "hello2"
# Expected: HTTP/1.1 200 OK (overwrite)

curl -si -X POST http://localhost:8080/b.txt -H "Content-Length: 5" --data "first"
# Expected: HTTP/1.1 201 Created (creates www/b.txt)

curl -si -X POST http://localhost:8080/b.txt -H "Content-Length: 6" --data "second"
# Expected: HTTP/1.1 201 Created (creates www/b(1).txt; www/b.txt unchanged)

CRED=$(printf '%s:%s' "$HTTP_AUTH_USER" "$HTTP_AUTH_PASS" | base64)
curl -si -X DELETE http://localhost:8080/a.txt -H "Authorization: Basic $CRED"
# Expected: HTTP/1.1 200 OK (file removed)
```

### Group B: Error conditions

Method enforcement (405), the request guards (411/413/414), and MIME rejection (415) are each shown with a command in §6 Implemented features. The conditions not shown there:

```bash
curl -si http://localhost:8080/does-not-exist.txt
# Expected: HTTP/1.1 404 Not Found

# 403: a file under www/ that the OS denies read access to returns 403.
# httpserver/handler.py checks os.access(fname, R_OK) before serving. Reproducing it
# depends on platform file permissions: POSIX `chmod 000 www/<file>` produces it, while
# on Windows chmod does not clear read access, so there is no portable one-liner here.
```

### Group C: Feature verification

Conditional 304 (via `If-None-Match` and via `If-Modified-Since`), gzip negotiation, and 503 load shedding each have a runnable command in §6 Implemented features. The 503 case is the one that needs setup: temporarily lower `MAX_REQUESTS` (for example to 2) in `httpserver/config.py`, restart the server, then issue several requests at once and observe a mix of `200` and `503` (each `503` carrying `Retry-After`); restore `MAX_REQUESTS` afterward.

### Group D: Security

Path safety is enforced by `is_safe_path()` in `httpserver/fileio.py`: the requested name is joined onto `ROOT`, resolved with `os.path.realpath` (collapsing `..` and following symlinks), and rejected unless the canonical result is still inside `ROOT` - this check runs before any file is opened. The server does not URL-decode the path, so percent-encoded sequences are treated as literal, nonexistent names.

```bash
curl -si "http://localhost:8080/../server.py"
# Expected: HTTP/1.1 404 (curl normalizes ../ client-side; no such file in www/)

curl -si "http://localhost:8080/../../etc/passwd"
# Expected: HTTP/1.1 403 or 404 - never the file contents

curl -si "http://localhost:8080/%2e%2e%2fserver.py"
# Expected: HTTP/1.1 404 (path not decoded; literal name not found)
```

```bash
CRED=$(printf '%s:%s' "$HTTP_AUTH_USER" "$HTTP_AUTH_PASS" | base64)
curl -si -X DELETE http://localhost:8080/test.txt -H "Authorization: Basic d3Jvbmc6Y3JlZHM="
# Expected: HTTP/1.1 401 Unauthorized (wrong credentials)

curl -si -X DELETE http://localhost:8080/test.txt
# Expected: HTTP/1.1 401 Unauthorized (missing Authorization header - handled, not a crash)
```

## Concurrency model

**Thread-per-connection.** Every connection returned by `accept()` is handed to a new daemon `threading.Thread` running `mythread()`, which owns that socket for its single request and then exits. Each request's locals (parsed headers, body, file handles) live only on its own thread, so requests do not share parsing state. This model blocks one thread per in-flight request on socket and disk I/O; because the work is I/O-bound rather than CPU-bound, the Python GIL is not the limiting factor - the limit is the thread count itself.

**Admission control.** Before starting a worker, `main()` evaluates `threading.active_count() < MAX_REQUESTS`. When the count is at the cap, the incoming connection receives a `503 Service Unavailable` with a `Retry-After` value chosen by `random.randint(50, 200)` and is then closed. The `Retry-After` is randomized so that many rejected clients do not all retry at the same instant and recreate the same overload.

**Shared-state protection.** Concurrent workers append to `var/cookies.txt` and `var/etag.csv` and write served files. A single `threading.Lock` in `httpserver/locks.py` is acquired around each of those write sections. Without it, two threads appending at once can interleave their bytes and leave a half-written or merged line in the file. One lock is enough here because these writes are short and infrequent relative to request handling, so contention on the lock is low and a finer-grained scheme is not warranted.

## Logging

Three log streams exist, one per level: `var/user.log` (INFO, level 0), `var/debug.log` (DEBUG, level 1), and `var/developer.log` (WARNING, level 2). The CLI log level selects which file `logging.basicConfig` writes to - it does not filter which messages are produced. Every request emits a `debug`, an `info`, and a `warning` record (request outcome, the request line and status, and a human-readable note), so the chosen file receives all three categories rather than a severity-filtered subset.

Rotation runs at startup, before logging is configured. For each stream, `logs_compression()` checks the existing log file's age against `EXPIRES` seconds; if it is older, the file is gzip-compressed into `var/<stream>logFiles/<stream>logfile<N>.gz` (with an incrementing index) and the original is deleted, after which a fresh log file is opened.

## Known limitations

- Thread-per-connection does not scale past roughly `MAX_REQUESTS` (20) concurrent connections; higher concurrency would require a thread pool or async I/O.
- No TLS. Basic auth credentials are sent base64-encoded in plaintext, so this server should not be exposed to an untrusted network.
- No keep-alive. Each connection handles exactly one request regardless of the `Connection` header value that is emitted; there is no read loop for a second request on the same socket.
- No chunked transfer encoding. Request bodies must carry a `Content-Length`.
- No content negotiation. `Accept` headers are not honored (`Accept-Encoding` is consulted only as a substring test for `gzip`, ignoring `q` values).
- No range requests or partial content (206).
- Shutdown does not drain in-flight requests - daemon worker threads are dropped when the process exits - and `SIGTERM` is not handled (only `SIGINT`/`SIGBREAK`).
- The test harness in `tests/` is print-based for its method checks and does not assert correctness end-to-end; `tests/CASES.md` is the reference for expected behavior.

## Technical highlights

- Raw BSD socket API: `AF_INET`/`SOCK_STREAM`, `bind`, `listen`, `accept`, non-blocking `recv` loop, `sendall`, `SO_REUSEADDR`.
- Hand-rolled CRLF HTTP parser and serializer - no `http.server`, no `urllib`, no `requests`.
- Header/body framing by a single split on `b"\r\n\r\n"`, with `Content-Length`-bounded body handling.
- First-match guard chain: URI length, method allow-list, HTTP version, path containment, redirect map.
- Conditional requests: `If-None-Match` with `*`/list/weak handling, plus `If-Modified-Since`, returning 304.
- Validator derived from `mtime`+`size`, so a modified file yields a different ETag.
- Negotiated gzip with `Content-Length` recomputed from the compressed bytes.
- Streaming delivery via a 64 KiB `read`/`sendall` loop - O(chunk) memory per connection regardless of file size.
- Canonical-path containment with `os.path.realpath` checked against `ROOT` before any file access.
- Constant-time credential comparison with `hmac.compare_digest`.
- Connection-admission control via `threading.active_count()` against a cap, with randomized `Retry-After`.
- Startup log rotation with `gzip` compression of aged files.

## What this project demonstrates

The point of building this was to implement the HTTP/1.1 request/response cycle and a thread-per-connection model directly on socket and threading primitives instead of on a framework - to work through how the pieces fit and where they break by writing them rather than importing them. The Technical highlights list the specific mechanisms; this section is about intent. The scope is a learning project, not a server meant for real traffic: the absences are choices, enumerated and reasoned about under Known limitations rather than left undiscovered. In a larger system it would sit as an origin tier that a separate proxy routes to.
