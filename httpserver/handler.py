import os
import sys
import base64
import hmac
import gzip
import shutil
import logging
from time import time, sleep

from . import config
from .protocol import http_versions, mime_types, Allow
from .locks import write_lock
from .fileio import (
    resolve,
    is_safe_path,
    should_compress,
    stream_file,
    write_file,
    post_name,
    file_type,
    modification_time,
)
from .responses import (
    make_body,
    error,
    allow_header,
    redirect_header,
    get_headers,
    not_modified_header,
    delete_header,
    ok,
    put_post,
)
from .etag import get_etag


def logs(n):
    if n == 0:
        logging.basicConfig(
            filename=config.LOG_FILES[0],
            format="[%(asctime)s]: %(message)s",
            level=logging.INFO,
        )
    elif n == 1:
        logging.basicConfig(
            filename=config.LOG_FILES[1],
            format="[%(asctime)s]: %(message)s",
            level=logging.DEBUG,
        )
    elif n == 2:
        logging.basicConfig(
            filename=config.LOG_FILES[2],
            format="[%(asctime)s]: %(message)s",
            level=logging.WARNING,
        )
    else:
        print("invalid logging level")
        sys.exit(0)


def logs_compression(log_file):
    if os.path.isfile(log_file):
        mtime = os.stat(log_file).st_mtime
        age = time() - mtime

        fname = os.path.splitext(os.path.basename(log_file))[0]
        LOG_DIRECTORY = os.path.join(config.VAR_DIR, fname + "logFiles")

        if int(age) > config.EXPIRES:
            if os.path.isdir(LOG_DIRECTORY):
                with open(log_file, "rb") as f_in:
                    number = len(os.listdir(LOG_DIRECTORY)) + 1
                    logfile_compress = LOG_DIRECTORY + f"/{fname}logfile{number}.gz"
                    with gzip.open(logfile_compress, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(log_file)
            else:
                os.mkdir(LOG_DIRECTORY)
                with open(log_file, "rb") as f_in:
                    logfile_compress = LOG_DIRECTORY + f"/{fname}logfile1.gz"
                    with gzip.open(logfile_compress, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(log_file)


flag = 1


def split_data(data):
    lines = data.split("\r\n")
    method = lines[0].split(" ")[0]
    version = lines[0].split(" ")[-1]
    filename = lines[0].split(" ")[1].replace("/", "", 1)

    # User-Agent is optional: a request without it must not crash the worker.
    if "User-Agent: " in data:
        user_agent = data.split("User-Agent: ")[1].split("\r\n")[0]
    else:
        user_agent = "-"

    if "Accept-Encoding: " in data:
        encoding = data.split("Accept-Encoding: ")[1].split("\r\n")[0]
    else:
        encoding = "-"

    if "Cookie: " in data:
        cookie = data.split("Cookie: ")[1].split("\r\n")[0]
    else:
        cookie = 0

    if "Content-Length: " in data:
        length = data.split("Content-Length: ")[1].split("\r\n")[0]
    else:
        length = 0

    return method, version, filename, user_agent, length, encoding, cookie


def auth(data):
    logging.debug('"checking delete authentication"')

    # Missing Authorization header => not authenticated (no crash).
    if "Authorization: Basic " not in data:
        return False

    # Malformed credential (bad base64, no ':' separator) => not authenticated.
    try:
        cred = data.split("Authorization: Basic ")[1].split("\r\n")[0]
        cred = base64.b64decode(cred).decode()
        user, password = cred.split(":", 1)
    except Exception:
        return False

    # Constant-time comparison; evaluate both halves before combining.
    user_ok = hmac.compare_digest(user, config.USERNAME)
    password_ok = hmac.compare_digest(password, config.PASSWORD)
    return user_ok and password_ok


no = ["", "favicon.ico"]

redirects = {"old.html": "new.html"}


def if_none_match(data):
    if "If-None-Match: " not in data:
        return None
    return data.split("If-None-Match: ")[1].split("\r\n")[0].strip()


def if_modified_since(data):
    if "If-Modified-Since: " not in data:
        return None
    return data.split("If-Modified-Since: ")[1].split("\r\n")[0].strip()


def etag_matches(inm, etag):
    if inm == "*":
        return True
    etag = etag.strip('"')
    for candidate in inm.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate.strip('"') == etag:
            return True
    return False


def helper(data, body, socket):
    # Defaults so the 500 handler never references an unbound local when a
    # malformed request line breaks parsing.
    method = version = fname = user_agent = "-"
    content_length = encoding = cookie = 0
    uri = ""

    try:
        method, version, fname, user_agent, content_length, encoding, cookie = (
            split_data(data)
        )

        uri = data.split("\r\n")[0].split(" ")[1]

        if len(uri) > config.MAX_URI:
            status_code = 414
            body = make_body(status_code)
            msg = error(version, fname, status_code, user_agent, body)
            socket.sendall(msg.encode())
            socket.sendall(body)

            logging.debug(f'{status_code} "uri length exceeded"')
            logging.info(
                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
            )
            logging.warning(f'{config.ip}:{config.port} "URI is too long."')

        elif method not in Allow:
            status_code = 405
            body = make_body(status_code)
            msg = allow_header(status_code, body, version, user_agent)
            socket.sendall(msg.encode())
            socket.sendall(body)
            logging.debug(f'{status_code} "method {method} not allowed."')
            logging.info(
                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
            )
            logging.warning(f'{config.ip}:{config.port} "method {method} not allowed."')

        elif version not in http_versions:
            status_code = 505
            body = make_body(status_code)
            msg = error(version, fname, status_code, user_agent, body)
            socket.sendall(msg.encode())
            socket.sendall(body)

            logging.debug(f'{status_code} "version not found"')
            logging.info(
                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
            )
            logging.warning(
                f'{config.ip}:{config.port} "{version} is not implemented."'
            )

        elif not is_safe_path(fname):
            status_code = 403
            body = make_body(status_code)
            msg = error(version, fname, status_code, user_agent, body)
            socket.sendall(msg.encode())
            socket.sendall(body)
            logging.debug(f'{status_code} "path traversal blocked"')
            logging.info(
                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
            )
            logging.warning(
                f'{config.ip}:{config.port} "blocked access outside document root: {fname}"'
            )

        elif fname in redirects and method in ("GET", "HEAD"):
            status_code = 301
            location = "/" + redirects[fname]
            body = make_body(status_code)
            msg = redirect_header(status_code, location, version, user_agent, body)
            socket.sendall(msg.encode())
            if method == "GET":
                socket.sendall(body)
            logging.debug(f'{status_code} "redirect {fname} -> {location}"')
            logging.info(
                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
            )
            logging.warning(
                f'{config.ip}:{config.port} "{fname} moved permanently to {location}."'
            )

        elif fname in no:
            msg = b"hello"
            socket.sendall(msg)

        else:
            if method == "GET" or method == "HEAD" or method == "DELETE":
                try:
                    if os.path.isfile(resolve(fname)):
                        # GET/HEAD only need read access; only DELETE needs write.
                        if os.access(resolve(fname), os.R_OK) and (
                            method != "DELETE" or os.access(resolve(fname), os.W_OK)
                        ):
                            if file_type(fname) in mime_types:
                                if method in ("GET", "HEAD"):
                                    inm = if_none_match(data)
                                    ims = if_modified_since(data)
                                    etag = get_etag(fname)
                                    if inm:
                                        not_modified = etag_matches(inm, etag)
                                    elif ims:
                                        not_modified = ims == modification_time(fname)
                                    else:
                                        not_modified = False
                                    if not_modified:
                                        status_code = 304
                                        msg = not_modified_header(
                                            fname, version, user_agent, etag
                                        )
                                        socket.sendall(msg.encode())
                                        logging.debug(f'{status_code} "not modified"')
                                        logging.info(
                                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                        )
                                        logging.warning(
                                            f'{config.ip}:{config.port} "{fname} not modified (If-None-Match)."'
                                        )
                                        return
                                    status_code = 200
                                    if should_compress(file_type(fname), encoding):
                                        with open(resolve(fname), "rb") as f:
                                            raw = f.read()
                                        gzipped = len(raw) > 0
                                        payload = gzip.compress(raw) if gzipped else raw
                                        msg = get_headers(
                                            status_code,
                                            fname,
                                            version,
                                            user_agent,
                                            cookie,
                                            len(payload),
                                            gzipped,
                                        )
                                        socket.sendall(msg.encode())
                                        if method == "GET":
                                            socket.sendall(payload)
                                    else:
                                        msg = get_headers(
                                            status_code,
                                            fname,
                                            version,
                                            user_agent,
                                            cookie,
                                            os.path.getsize(resolve(fname)),
                                            False,
                                        )
                                        socket.sendall(msg.encode())
                                        if method == "GET":
                                            stream_file(socket, fname)
                                    if method == "GET":
                                        logging.warning(
                                            f'{config.ip}:{config.port} "{fname} was accessed successfully."'
                                        )
                                    else:
                                        logging.warning(
                                            f'{config.ip}:{config.port} "only headers for {fname} were asked."'
                                        )
                                    logging.debug(
                                        f'{status_code} "{method} successful"'
                                    )
                                    logging.info(
                                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                    )
                                    return
                                elif method == "DELETE":
                                    if auth(data):
                                        status_code = 200
                                        msg = delete_header(
                                            status_code,
                                            fname,
                                            version,
                                            user_agent,
                                            cookie,
                                        )
                                        # Serialize the removal with all other shared-file mutations.
                                        with write_lock:
                                            os.remove(resolve(fname))
                                        socket.sendall(msg.encode())
                                        logging.debug(
                                            f'{status_code} "delete successful"'
                                        )
                                        logging.info(
                                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                        )
                                        logging.warning(
                                            f'{config.ip}:{config.port} "{fname} deleted."'
                                        )
                                        return
                                    else:
                                        status_code = 401
                                        body = make_body(status_code)
                                        msg = error(
                                            version,
                                            fname,
                                            status_code,
                                            user_agent,
                                            body,
                                        )
                                        socket.sendall(msg.encode())
                                        socket.sendall(body)
                                        logging.debug(f'{status_code} "unauthorized"')
                                        logging.info(
                                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                        )
                                        logging.warning(
                                            f'{config.ip}:{config.port} "authorization failed for delete."'
                                        )
                                        return
                            else:
                                status_code = 415
                                body = make_body(status_code)
                                msg = error(
                                    version, fname, status_code, user_agent, body
                                )
                                socket.sendall(msg.encode())
                                socket.sendall(body)
                                logging.debug(f'{status_code} "unsupported media type"')
                                logging.info(
                                    f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                )
                                logging.warning(
                                    f'{config.ip}:{config.port} "{fname} is of an unsupported media type."'
                                )
                                return
                        else:
                            status_code = 403
                            body = make_body(status_code)
                            msg = error(version, fname, status_code, user_agent, body)
                            socket.sendall(msg.encode())
                            socket.sendall(body)
                            logging.debug(f'{status_code} "forbidden"')
                            logging.info(
                                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                            )
                            logging.warning(
                                f'{config.ip}:{config.port} "{fname} does not have read/write permissions."'
                            )
                            return
                    else:
                        status_code = 404
                        body = make_body(status_code)
                        msg = error(version, fname, status_code, user_agent, body)
                        socket.sendall(msg.encode())
                        socket.sendall(body)
                        logging.debug(f'{status_code} "not found"')
                        logging.info(
                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                        )
                        logging.warning(
                            f'{config.ip}:{config.port} "{fname} was not found."'
                        )
                        return

                except Exception:
                    status_code = 400
                    body = make_body(status_code)
                    msg = error(version, fname, status_code, user_agent, body)
                    socket.sendall(msg.encode())
                    socket.sendall(body)
                    logging.debug(f'{status_code} "Bad Request in {method}."')
                    logging.info(
                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                    )
                    logging.warning(
                        f'{config.ip}:{config.port} "Bad Request in {method}."'
                    )
                    return

            elif method == "PUT":
                try:
                    if content_length:
                        if len(body) < config.MAX_PAYLOAD:
                            if os.path.isfile(resolve(fname)):
                                if os.access(resolve(fname), os.R_OK) and os.access(
                                    resolve(fname), os.W_OK
                                ):
                                    status_code = 200
                                    write_file(fname, body)
                                    msg = ok(
                                        status_code, fname, version, user_agent, cookie
                                    )
                                    socket.sendall(msg.encode())
                                    logging.debug(
                                        f'{status_code} "created in put(existing file)"'
                                    )
                                    logging.info(
                                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                    )
                                    logging.warning(
                                        f'{config.ip}:{config.port} "{fname} was modified successfully."'
                                    )
                                    return

                                else:
                                    status_code = 403
                                    resp_body = make_body(status_code)
                                    msg = error(
                                        version,
                                        fname,
                                        status_code,
                                        user_agent,
                                        resp_body,
                                    )
                                    socket.sendall(msg.encode())
                                    socket.sendall(resp_body)
                                    logging.debug(f'{status_code} "forbidden in put"')
                                    logging.info(
                                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                    )
                                    logging.warning(
                                        f'{config.ip}:{config.port} "{fname} does not have write permissions."'
                                    )
                                    return
                            else:
                                status_code = 201
                                write_file(fname, body)
                                resp_body = make_body(status_code)
                                msg = put_post(
                                    status_code,
                                    fname,
                                    version,
                                    user_agent,
                                    resp_body,
                                    cookie,
                                )
                                socket.sendall(msg.encode())
                                socket.sendall(resp_body)
                                logging.debug(
                                    f'{status_code} "created in put(new file)"'
                                )
                                logging.info(
                                    f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                )
                                logging.warning(
                                    f'{config.ip}:{config.port} "{fname} was created successfully."'
                                )
                                return
                        else:
                            status_code = 413
                            resp_body = make_body(status_code)
                            msg = error(
                                version, fname, status_code, user_agent, resp_body
                            )
                            socket.sendall(msg.encode())
                            socket.sendall(resp_body)
                            logging.debug(f'{status_code} "paylod size exceeded"')
                            logging.info(
                                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                            )
                            logging.warning(
                                f'{config.ip}:{config.port} "{fname} has size {len(body)} which exceeds max payload size({config.MAX_PAYLOAD})."'
                            )
                            return
                    else:
                        status_code = 411
                        resp_body = make_body(status_code)
                        msg = error(version, fname, status_code, user_agent, resp_body)
                        socket.sendall(msg.encode())
                        socket.sendall(resp_body)
                        logging.debug(f'{status_code} "body length is 0"')
                        logging.info(
                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                        )
                        logging.warning(
                            f'{config.ip}:{config.port} "{fname} is empty."'
                        )
                        return
                except Exception:
                    status_code = 400
                    body = make_body(status_code)
                    msg = error(version, fname, status_code, user_agent, body)
                    socket.sendall(msg.encode())
                    socket.sendall(body)
                    logging.debug(f'{status_code} "Bad Request in {method}."')
                    logging.info(
                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                    )
                    logging.warning(
                        f'{config.ip}:{config.port} "Bad Request in {method}."'
                    )
                    return

            elif method == "POST":
                try:
                    if content_length:
                        if len(body) < config.MAX_PAYLOAD:
                            if os.path.isfile(resolve(fname)):
                                if os.access(resolve(fname), os.R_OK) and os.access(
                                    resolve(fname), os.W_OK
                                ):
                                    status_code = 201

                                    new = post_name(fname)

                                    write_file(new, body)
                                    resp_body = make_body(status_code)
                                    msg = put_post(
                                        status_code,
                                        new,
                                        version,
                                        user_agent,
                                        resp_body,
                                        cookie,
                                    )
                                    socket.sendall(msg.encode())
                                    socket.sendall(resp_body)
                                    logging.debug(f'{status_code} "created in post"')
                                    logging.info(
                                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                    )
                                    logging.warning(
                                        f'{config.ip}:{config.port} "A new file named {new} was created."'
                                    )
                                    return
                                else:
                                    status_code = 403
                                    resp_body = make_body(status_code)
                                    msg = error(
                                        version,
                                        fname,
                                        status_code,
                                        user_agent,
                                        resp_body,
                                    )
                                    socket.sendall(msg.encode())
                                    socket.sendall(resp_body)
                                    logging.debug(f'{status_code} "forbidden in post"')
                                    logging.info(
                                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                    )
                                    logging.warning(
                                        f'{config.ip}:{config.port} "{fname} does not have write permissions."'
                                    )
                                    return
                            else:
                                status_code = 201
                                write_file(fname, body)
                                resp_body = make_body(status_code)
                                msg = put_post(
                                    status_code,
                                    fname,
                                    version,
                                    user_agent,
                                    resp_body,
                                    cookie,
                                )
                                socket.sendall(msg.encode())
                                socket.sendall(resp_body)
                                logging.debug(f'{status_code} "created in put"')
                                logging.info(
                                    f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                                )
                                logging.warning(
                                    f'{config.ip}:{config.port} "A new file named {fname} was created."'
                                )
                                return
                        else:
                            status_code = 413
                            resp_body = make_body(status_code)
                            msg = error(
                                version, fname, status_code, user_agent, resp_body
                            )
                            socket.sendall(msg.encode())
                            socket.sendall(resp_body)
                            logging.debug(f'{status_code} "paylod size exceeded"')
                            logging.info(
                                f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                            )
                            logging.warning(
                                f'{config.ip}:{config.port} "{fname} has size {len(body)} which exceeds max payload size({config.MAX_PAYLOAD})."'
                            )
                            return
                    else:
                        status_code = 411
                        resp_body = make_body(status_code)
                        msg = error(version, fname, status_code, user_agent, resp_body)
                        socket.sendall(msg.encode())
                        socket.sendall(resp_body)
                        logging.debug(f'{status_code} "body length is 0"')
                        logging.info(
                            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                        )
                        logging.warning(
                            f'{config.ip}:{config.port} "{fname} is empty."'
                        )
                        return
                except Exception:
                    status_code = 400
                    body = make_body(status_code)
                    msg = error(version, fname, status_code, user_agent, body)
                    socket.sendall(msg.encode())
                    socket.sendall(body)
                    logging.debug(f'{status_code} "Bad Request in {method}."')
                    logging.info(
                        f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
                    )
                    logging.warning(
                        f'{config.ip}:{config.port} "Bad Request in {method}."'
                    )
                    return
            # The `method not in Allow` guard above already returns 405 for any
            # method outside GET/HEAD/DELETE/PUT/POST, so no further branch runs.

        if version == "HTTP/1.0":
            socket.close()

    except Exception:
        status_code = 500
        body = make_body(status_code)
        msg = error(version, fname, status_code, user_agent, body)
        socket.sendall(msg.encode())
        socket.sendall(body)
        logging.debug(f'{status_code} "internal server error"')
        logging.info(
            f'{config.ip}:{config.port} "{method} {version} {fname}" {status_code}'
        )
        logging.warning(
            f'{config.ip}:{config.port} "An internal server error occurred."'
        )
        return


def mythread(connectionSocket):
    connectionSocket.setblocking(0)
    data = bytes("", "utf-8")
    timeout = 2
    begin = time()
    while True:
        if data and time() - begin > timeout:
            break
        elif time() - begin > 2 * timeout - 1:
            break
        try:
            t = connectionSocket.recv(8192)
            if t:
                data += t
                begin = time()
            else:
                sleep(0.1)
        except OSError:
            # Non-blocking socket with no data ready (BlockingIOError) or a
            # transient connection error; keep polling until the timeout.
            pass

    if not data:
        return
    # Tolerate a missing header/body separator without crashing the worker.
    try:
        decoded = data.decode()
        parts = decoded.split("\r\n\r\n", 1)
        data = parts[0]
        body = parts[1] if len(parts) > 1 else ""
    except UnicodeDecodeError:
        parts = data.split(b"\r\n\r\n", 1)
        data = parts[0].decode(errors="replace")
        body = parts[1] if len(parts) > 1 else b""

    # Restore blocking mode before responding: a large streamed sendall on a
    # non-blocking socket would raise BlockingIOError once the send buffer fills.
    connectionSocket.setblocking(True)
    helper(data, body, connectionSocket)
