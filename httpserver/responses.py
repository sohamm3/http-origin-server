import uuid
from time import strftime

from . import config
from .protocol import status_codes, status_messages
from .locks import write_lock
from .fileio import file_length, file_type, file_location, modification_time
from .etag import get_etag


def date_time():
    return strftime("%a, %d %b %Y %H:%M:%S %Z")


def make_body(status_code):
    title = f"{status_code} {status_codes[status_code]}"
    detail = status_messages.get(status_code, status_codes[status_code])
    html = (
        f"<!DOCTYPE html><html><head><title>{title}</title></head>"
        f"<body><h1>{title}</h1><p>{detail}</p></body></html>"
    )
    return html.encode()


def write_cookie():
    id = str(uuid.uuid1())
    # Serialize appends so concurrent Set-Cookie writes can't merge a line.
    with write_lock:
        with open(config.COOKIES_FILE, "a+") as cookiefile:
            cookiefile.write(id + "\n")
    return id


def error(version, filename, status_code, user_agent, body):
    err = f"{version} {status_code} {status_codes[status_code]}\r\n"
    err += "Date: " + date_time() + "\r\n"
    err += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    err += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    err += "User-Agent: " + user_agent + "\r\n"
    err += "Content-Length: " + str(len(body)) + "\r\n"
    err += "Connection: Keep-Alive\r\n"
    err += "Content-Type: text/html; charset=utf-8\r\n\r\n"
    return err


def get_headers(
    status_code, filename, version, user_agent, cookie, content_length, gzipped
):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Accept: */* \r\n"
    header += "Last-Modified: " + modification_time(filename) + "\r\n"
    header += "Content-Length: " + str(content_length) + "\r\n"
    header += "ETag: " + get_etag(filename) + "\r\n"
    if gzipped:
        header += "Content-Encoding: gzip\r\n"
    header += "Accept-Charset : UTF-8\r\n"
    header += "Range: bytes=0-\r\n"
    header += "Accept-Ranges: bytes\r\n"

    if cookie == 0:
        header += "Set-Cookie: id=" + write_cookie() + "; Max-Age=120\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Content-Location: " + file_location(filename) + "\r\n"
    header += "Content-Type: " + str(file_type(filename)) + "\r\n\r\n"
    return header


def put_post(status_code, filename, version, user_agent, body, cookie):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Accept: */* \r\n"
    header += "Last-Modified: " + modification_time(filename) + "\r\n"
    header += "Content-Length: " + str(len(body)) + "\r\n"

    if cookie == 0:
        header += "Set-Cookie: id=" + write_cookie() + "; Max-Age=120\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Location: " + file_location(filename) + "\r\n"
    header += "Content-Type: " + str(file_type(filename)) + "\r\n\r\n"
    return header


def ok(status_code, filename, version, user_agent, cookie):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Accept: */* \r\n"
    header += "Last-Modified: " + modification_time(filename) + "\r\n"
    header += "Content-Length: " + file_length(filename) + "\r\n"

    if cookie == 0:
        header += "Set-Cookie: id=" + write_cookie() + "; Max-Age=120\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Content-Location: " + file_location(filename) + "\r\n"
    header += "Content-Type: " + str(file_type(filename)) + "\r\n\r\n"
    return header


def delete_header(status_code, filename, version, user_agent, cookie):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Accept: */* \r\n"

    if cookie == 0:
        header += "Set-Cookie: id=" + write_cookie() + "; Max-Age=120\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Content-Type: " + str(file_type(filename)) + "\r\n\r\n"
    return header


def allow_header(status_code, body, version, user_agent):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Accept: */* \r\n"
    header += "Allow: GET, HEAD, DELETE, PUT, POST\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Content-Length: " + str(len(body)) + "\r\n"
    header += "Content-Type: text/html; charset=utf-8\r\n\r\n"
    return header


def redirect_header(status_code, location, version, user_agent, body):
    header = f"{version} {status_code} {status_codes[status_code]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "Location: " + location + "\r\n"
    header += "Content-Length: " + str(len(body)) + "\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n"
    header += "Content-Type: text/html; charset=utf-8\r\n\r\n"
    return header


def not_modified_header(filename, version, user_agent, etag):
    header = f"{version} 304 {status_codes[304]}\r\n"
    header += "Date: " + date_time() + "\r\n"
    header += "Host: " + str(config.ip) + ":" + str(config.port) + "\r\n"
    header += "Server: Apache/2.4.46 (Ubuntu) \r\n"
    header += "User-Agent: " + user_agent + "\r\n"
    header += "ETag: " + etag + "\r\n"
    header += "Last-Modified: " + modification_time(filename) + "\r\n"

    if version == "HTTP/1.0":
        conn = "close"
    else:
        conn = "keep-alive"

    header += "Connection: " + conn + "\r\n\r\n"
    return header
