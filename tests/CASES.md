# HTTP Server: Behavior Cases

This file is a reference for manual verification and for understanding the server's expected HTTP behavior. It records, per feature, the implementing module/function, the happy-path request and response, and the error and edge cases with their expected status codes. It is documentation, not executable code. The runtime harness in `tests/client_tests.py` exercises these behaviors against a running server. Some of its checks only print the response for manual inspection without asserting (the core method calls `get`/`head`/`put`/`post`/`delete`/`unauthorized` and several status-guard checks such as 405/411/414/415/505/non-persistent HEAD); many others do assert on status, headers, or body (conditional GET, gzip, streaming, path traversal, the 403/permission check, missing-`Authorization` and no-`User-Agent` handling, redirects, HEAD correctness, and concurrency). It is therefore not a complete automated test suite - this document is the authoritative description of the expected behavior that the harness partially exercises.

Conventions used below:

- The document root is `www/`; all served paths resolve under it (`fileio.resolve`).
- Default credentials are `HTTP_AUTH_USER` / `HTTP_AUTH_PASS` (defaults `soham` / `Soham@2020`).
- `MAX_URI = 50`, `MAX_PAYLOAD = 512000`, `MAX_REQUESTS = 20`, `EXPIRES = 43200` (`httpserver/config.py`).
- The body-size guard compares the number of bytes actually received, not the `Content-Length` header value.

---

## 1. GET static file

**Implementation:** `handler.helper` (GET branch) → `responses.get_headers` + `fileio.stream_file` (or buffered+gzip path)
**Happy path**
Input: `GET /test.txt HTTP/1.1`
Output: `200 OK`; `Content-Type: text/plain`; `Content-Length: <size>`; `ETag`, `Last-Modified`, `Content-Location`; body = file bytes.
**Error / edge cases**

| Input condition                                | Expected output                                 |
| ---------------------------------------------- | ----------------------------------------------- |
| `GET /test.txt` (exists, readable, known type) | `200 OK`, body                                  |
| `GET /missing.txt` (not present)               | `404 Not Found`                                 |
| File present but not readable                  | `403 Forbidden`                                 |
| Path resolves outside `www/` (e.g. `/../x`)    | `403 Forbidden`                                 |
| Known-but-unsupported MIME (e.g. `.exe`)       | `415 Unsupported Media Type`                    |
| Request line with no `User-Agent` header       | `200 OK` (User-Agent optional, defaults to `-`) |

---

## 2. HEAD (no body rule)

**Implementation:** `handler.helper` (HEAD branch) → `responses.get_headers` (headers only, no body sent)
**Happy path**
Input: `HEAD /test.txt HTTP/1.1`
Output: `200 OK`; identical headers to GET including the same `Content-Length` (the size GET would send, compressed length if gzip negotiated); **no response body**.
**Error / edge cases**

| Input condition                               | Expected output                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------------- |
| `HEAD /test.txt`                              | `200 OK`, headers, no body                                                      |
| `HEAD /missing.txt`                           | `404 Not Found`, no body                                                        |
| `HEAD` with matching `If-None-Match`          | `304 Not Modified`, no body                                                     |
| `HEAD /test.txt` with `Accept-Encoding: gzip` | `200 OK`, `Content-Encoding: gzip`, `Content-Length` = compressed size, no body |
| `HEAD /old.html` (redirected resource)        | `301 Moved Permanently`, `Location: /new.html`, no body                         |

---

## 3. PUT create / PUT overwrite

**Implementation:** `handler.helper` (PUT branch) → `fileio.write_file`; `responses.put_post` (create) / `responses.ok` (overwrite)
**Happy path**
Input: `PUT /put_test.txt` with `Content-Length: 13` and a body (new path)
Output: `201 Created`; `Location` header. Re-PUT to an existing writable path → `200 OK`.
**Error / edge cases**

| Input condition                                        | Expected output                                  |
| ------------------------------------------------------ | ------------------------------------------------ |
| PUT new file, valid `Content-Length` + body            | `201 Created`                                    |
| PUT existing writable file                             | `200 OK` (overwrite)                             |
| PUT existing non-writable file                         | `403 Forbidden`                                  |
| PUT with **no `Content-Length`** header                | `411 Length Required`                            |
| Body length exactly `511999` (one under `MAX_PAYLOAD`) | `200`/`201` (accepted)                           |
| Body length exactly `512000` (`MAX_PAYLOAD`)           | `413 Payload Too Large` (guard is `<`, not `<=`) |
| Body length `512001` (one over)                        | `413 Payload Too Large`                          |
| Target path outside `www/`                             | `403 Forbidden`                                  |

---

## 4. POST new file / POST collision naming

**Implementation:** `handler.helper` (POST branch) → `fileio.post_name` (collision name) + `fileio.write_file`; `responses.put_post`
**Happy path**
Input: `POST /post_test.txt` with `Content-Length` + body (path does not exist)
Output: `201 Created`; new file `www/post_test.txt`.
**Error / edge cases**

| Input condition                    | Expected output                                                |
| ---------------------------------- | -------------------------------------------------------------- |
| POST to non-existing path          | `201 Created`, file written at that name                       |
| POST to existing path (collision)  | `201 Created`, new file `post_test(1).txt`; original unchanged |
| Repeated collision                 | next index, e.g. `post_test(2).txt`                            |
| POST with no `Content-Length`      | `411 Length Required`                                          |
| Body at/over `MAX_PAYLOAD`         | `413 Payload Too Large`                                        |
| POST to existing non-writable file | `403 Forbidden`                                                |

---

## 5. DELETE authorized / unauthorized / missing header

**Implementation:** `handler.helper` (DELETE branch) → `handler.auth` (`hmac.compare_digest`); `responses.delete_header`
**Happy path**
Input: `DELETE /put_test.txt` with `Authorization: Basic base64(user:pass)` (correct creds)
Output: `200 OK`; file removed from `www/`.
**Error / edge cases**

| Input condition                            | Expected output                                                                                |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Correct credentials, file exists+writable  | `200 OK`, file deleted                                                                         |
| Wrong credentials                          | `401 Unauthorized`                                                                             |
| **Missing `Authorization` header**         | `401 Unauthorized` (not 400; missing credentials are an auth failure, not a malformed request) |
| Malformed credential (bad base64 / no `:`) | `401 Unauthorized` (decode failure → not authenticated, no crash)                              |
| DELETE on a non-writable file              | `403 Forbidden` (permission checked before auth)                                               |
| DELETE on a missing file                   | `404 Not Found`                                                                                |

---

## 6. 405 Method Not Allowed + Allow header

**Implementation:** `handler.helper` (`method not in Allow`) → `responses.allow_header`; `protocol.Allow`
**Happy path**
Input: `PATCH /test.txt HTTP/1.1`
Output: `405 Method Not Allowed`; `Allow: GET, HEAD, DELETE, PUT, POST`; HTML body.
**Error / edge cases**

| Input condition                                         | Expected output                                          |
| ------------------------------------------------------- | -------------------------------------------------------- |
| `PATCH` / `OPTIONS` / `TRACE` / any verb not in `Allow` | `405`, `Allow` header listing the five supported methods |
| Lowercase `get`                                         | `405` (method match is case-sensitive)                   |
| Unsupported HTTP version (e.g. `HTTP/2.1`)              | `505 HTTP Version not Supported` (checked after method)  |

---

## 7. 411 / 413 / 414 request guards

**Implementation:** `handler.helper` (URI-length check; `content_length` truthiness; `len(body)` vs `config.MAX_PAYLOAD`)
**Happy path**
Input: Well-formed request with a present `Content-Length`, body under the limit, URI ≤ 50 chars.
Output: normal status for the method (`200`/`201`).
**Error / edge cases**

| Input condition                                       | Expected output                                                                    |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| URI length exactly 50                                 | accepted (`> MAX_URI` is false)                                                    |
| URI length 51 (one over)                              | `414 URI Too Long`                                                                 |
| PUT/POST with no `Content-Length`                     | `411 Length Required`                                                              |
| Body exactly `512000` bytes                           | `413 Payload Too Large`                                                            |
| Body `511999` bytes                                   | accepted                                                                           |
| `Content-Length` present but a malformed request line | `400 Bad Request` (parse failure path) / `500` if parsing raises before validation |

Note: a body sent via `curl --data` always carries an auto-generated `Content-Length`; testing `411` requires a client that omits the header (e.g. a raw socket).

---

## 8. 415 MIME rejection

**Implementation:** `handler.helper` (`file_type(fname) in mime_types`); `fileio.file_type` (`mimetypes.guess_type`); `protocol.mime_types`
**Happy path**
Input: `GET /test.txt` (`text/plain` ∈ `mime_types`)
Output: `200 OK`.
**Error / edge cases**

| Input condition                                         | Expected output                                                              |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| GET file whose guessed type ∈ `mime_types`              | served (`200`)                                                               |
| GET existing file with unsupported type (`.exe`, `.pp`) | `415 Unsupported Media Type`                                                 |
| GET file with no guessable extension (type `None`)      | `415` (`None` ∉ `mime_types`)                                                |
| PUT of any extension                                    | not MIME-checked; `201`/`200` (MIME enforced on GET/HEAD read, not on write) |

---

## 9. Conditional GET: ETag (If-None-Match)

**Implementation:** `handler.if_none_match` + `handler.etag_matches` + `etag.get_etag` (mtime+size validator) → `responses.not_modified_header`
**Happy path**
Input: `GET /test.txt` with `If-None-Match: "<mtime>-<size>"` matching the current file
Output: `304 Not Modified`; `ETag`, `Last-Modified`; no body.
**Error / edge cases**

| Input condition                         | Expected output                                                   |
| --------------------------------------- | ----------------------------------------------------------------- |
| `If-None-Match` equals current ETag     | `304`, no body                                                    |
| `If-None-Match: *`                      | `304` (matches any existing resource)                             |
| Comma-list containing the current ETag  | `304`                                                             |
| Weak validator `W/"<etag>"`             | `304` (weak prefix stripped before compare)                       |
| File modified after the ETag was issued | `200 OK` with a new ETag (validator is mtime+size, so it changes) |
| `If-None-Match` not matching            | `200 OK`, full body                                               |
| No `If-None-Match` header               | `200 OK`, full body                                               |

---

## 10. Conditional GET: Last-Modified (If-Modified-Since)

**Implementation:** `handler.if_modified_since` + `fileio.modification_time` → `responses.not_modified_header`
**Happy path**
Input: `GET /test.txt` with `If-Modified-Since: <value previously returned as Last-Modified>`
Output: `304 Not Modified`; no body.
**Error / edge cases**

| Input condition                                               | Expected output                                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `If-Modified-Since` equals the file's current `Last-Modified` | `304`, no body                                                                                   |
| File modified since (different `Last-Modified`)               | `200 OK`, new `Last-Modified`                                                                    |
| Both `If-None-Match` and `If-Modified-Since` present          | `If-None-Match` takes precedence; `If-Modified-Since` evaluated only when `If-None-Match` absent |
| Malformed / unrecognized date value                           | treated as not matching → `200 OK`                                                               |
| No `If-Modified-Since` header                                 | `200 OK`                                                                                         |

---

## 11. gzip response compression

**Implementation:** `fileio.should_compress` (`protocol.compressible_types`) + `handler.helper` (`gzip.compress`) + `responses.get_headers` (`Content-Encoding: gzip`)
**Happy path**
Input: `GET /test.txt` with `Accept-Encoding: gzip`
Output: `200 OK`; `Content-Encoding: gzip`; `Content-Length` = compressed size; body = gzip stream that decompresses to the file.
**Error / edge cases**

| Input condition                                                                                      | Expected output                                                        |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Compressible type (`text/html`,`text/plain`,`text/css`,`application/json`) + `Accept-Encoding: gzip` | `200`, `Content-Encoding: gzip`, compressed body                       |
| `Accept-Encoding: gzip, deflate`                                                                     | `200`, gzip used (substring match)                                     |
| No `Accept-Encoding` / `identity`                                                                    | `200`, no `Content-Encoding`, uncompressed body                        |
| Non-compressible type (image/video/pdf) + `Accept-Encoding: gzip`                                    | `200`, **no** `Content-Encoding`, raw body                             |
| Empty compressible file + gzip                                                                       | `200`, no `Content-Encoding` (empty body not compressed)               |
| `Accept-Encoding: gzip;q=0` (explicit refusal)                                                       | `200`, gzip still applied (q-values not parsed - substring match only) |
| `304` response with gzip requested                                                                   | `304`, no `Content-Encoding`, no body                                  |

---

## 12. Streaming file delivery

**Implementation:** `fileio.stream_file` (64 KiB chunked reads); `handler.helper` (uncompressed branch); `handler.mythread` restores blocking mode before sending
**Happy path**
Input: `GET /video.mp4`
Output: `200 OK`; `Content-Length` = file size; body delivered in 64 KiB chunks (file never fully buffered in memory).
**Error / edge cases**

| Input condition                                            | Expected output                                                                                                                     |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Large non-compressible file                                | `200`, `Content-Length` = exact file size, byte-identical body, chunked                                                             |
| `HEAD` on a large file                                     | `200`, correct `Content-Length`, no body                                                                                            |
| Conditional request on a streamed resource (matching ETag) | `304`, no body (no streaming)                                                                                                       |
| Large compressible text + gzip                             | buffered, gzipped, `Content-Encoding: gzip` (gzip path is buffered to compute `Content-Length`; only the uncompressed path streams) |

---

## 13. Path traversal protection

**Implementation:** `fileio.is_safe_path` (`os.path.realpath` containment under `config.ROOT`, `normcase`)
**Happy path**
Input: `GET /test.txt`
Output: `200 OK` (resolves inside `www/`).
**Error / edge cases**

| Input condition                                                  | Expected output                                                                   |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Path resolving outside root (`../x`, `..\\..\\x`, absolute path) | `403 Forbidden`                                                                   |
| `GET /../server.py` via curl (client normalizes to `/server.py`) | `404 Not Found` (no such file in `www/`)                                          |
| URL-encoded `GET /%2e%2e%2fserver.py`                            | `404 Not Found` (path is not URL-decoded; treated as a literal, nonexistent name) |
| Symlink inside `www/` pointing outside                           | `403 Forbidden` (`realpath` follows the link before the containment check)        |
| `""` (root path) / `favicon.ico`                                 | special-cased: returns the literal bytes `hello`                                  |

---

## 14. 503 load shedding + Retry-After

**Implementation:** `server.main` (`threading.active_count() < config.MAX_REQUESTS`); inline 503 response with `Retry-After`
**Happy path**
Input: Concurrent request count within `MAX_REQUESTS`.
Output: normal `200` per request.
**Error / edge cases**

| Input condition                                      | Expected output                                                         |
| ---------------------------------------------------- | ----------------------------------------------------------------------- |
| Active worker count below `MAX_REQUESTS`             | request served normally                                                 |
| New connection when `active_count() >= MAX_REQUESTS` | `503 Service Unavailable`; `Retry-After: <50–200>`; `Connection: Close` |
| Burst of concurrent requests beyond the cap          | some succeed, the rest receive `503` with `Retry-After`                 |

---

## 15. Cookie issuance and suppression on repeat

**Implementation:** `responses.write_cookie` (appends a UUID to `var/cookies.txt` under the lock) + `responses.get_headers` (`Set-Cookie` only when `cookie == 0`)
**Happy path**
Input: `GET /test.txt` with no `Cookie` header
Output: `200 OK`; `Set-Cookie: id=<uuid>; Max-Age=120`; one UUID appended to `var/cookies.txt`.
**Error / edge cases**

| Input condition                        | Expected output                                                                              |
| -------------------------------------- | -------------------------------------------------------------------------------------------- |
| Request without a `Cookie` header      | `Set-Cookie` issued; `cookies.txt` grows by one line                                         |
| Request with a `Cookie` header present | **no** `Set-Cookie` in the response; `cookies.txt` not appended                              |
| Empty `Cookie:` header value           | client may drop the empty header; if no `Cookie:` reaches the server, a new cookie is issued |
| Many concurrent first-time requests    | each gets a distinct UUID; `cookies.txt` lines remain well-formed (lock serializes appends)  |

---

## 16. Log rotation trigger

**Implementation:** `handler.logs_compression` (run at startup for each log in `config.LOG_FILES`); `config.EXPIRES`
**Happy path**
Input: Server start when an existing `var/<name>.log` is older than `EXPIRES` seconds.
Output: the log is gzip-compressed into `var/<name>logFiles/<name>logfile<N>.gz`, the original is removed, and a fresh log is opened.
**Error / edge cases**

| Input condition                     | Expected output                                                |
| ----------------------------------- | -------------------------------------------------------------- |
| Log file age `> EXPIRES` at startup | compressed to `.gz` in `var/<name>logFiles/`, original removed |
| Log file age `<= EXPIRES`           | left in place, not compressed                                  |
| No existing log file                | nothing to compress (no error)                                 |
| Archive directory already exists    | next archive numbered `<N+1>`                                  |
| Repeated rotations                  | incrementing archive index (`logfile1.gz`, `logfile2.gz`, …)   |

---

## 17. Graceful shutdown behavior

**Implementation:** `server.main` (`try/except KeyboardInterrupt … finally: server.close()`) + `server._request_shutdown` (handler for `SIGINT`, and `SIGBREAK` where available)
**Happy path**
Input: `SIGINT` (Ctrl+C) or `SIGBREAK` (Ctrl+Break) sent to the server process.
Output: prints `server stopped`, closes the listening socket, exits with code 0; no traceback.
**Error / edge cases**

| Input condition                     | Expected output                                                                                                                           |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `SIGINT` / `SIGBREAK` while idle    | clean exit within ~1s (bounded `accept()` timeout makes the signal observable)                                                            |
| Signal while a request is in flight | server exits promptly; the in-flight request is **not** drained - worker threads are daemon threads and are dropped at exit               |
| `SIGTERM`                           | not handled by a custom handler; default process termination (no `server stopped` message). On Windows there is no POSIX `SIGTERM`/`kill` |
| Immediate restart after shutdown    | binds the same port without `TIME_WAIT` delay (`SO_REUSEADDR`)                                                                            |

Note: The design favors prompt, non-hanging shutdown (daemon workers) over draining in-flight requests; draining and `SIGTERM` handling are not implemented.
