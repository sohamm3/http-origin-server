import os
import mimetypes
from glob import glob
from time import strftime, localtime

from . import config
from .locks import write_lock
from .protocol import binary_extensions, compressible_types


def resolve(filename):
    return os.path.join(config.ROOT, filename)


def file_length(filename):
    return str(os.path.getsize(resolve(filename)))


def file_type(filename):
    type, encoding = mimetypes.guess_type(filename)
    return type


def file_location(filename):
    return os.path.abspath(resolve(filename))


def modification_time(filename):
    t = os.path.getmtime(resolve(filename))
    return strftime("%a, %d %b %Y %H:%M:%S %Z", localtime(t))


def is_safe_path(filename):
    # Confirm the requested name stays inside ROOT after resolving ".." segments,
    # absolute-path overrides, and symlinks. normcase handles Windows paths.
    root = os.path.realpath(config.ROOT)
    target = os.path.realpath(os.path.join(root, filename))
    root_cmp = os.path.normcase(root)
    target_cmp = os.path.normcase(target)
    return target_cmp == root_cmp or target_cmp.startswith(root_cmp + os.sep)


def extension(filename):
    return os.path.splitext(filename)[1].lstrip(".").lower()


def write_file(filename, data):
    mode = "wb" if extension(filename) in binary_extensions else "w"
    # Serialize writes so concurrent PUT/POST to the same path can't interleave.
    with write_lock:
        with open(resolve(filename), mode) as f:
            f.write(data)


def stream_file(sock, filename):
    with open(resolve(filename), "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sock.sendall(chunk)


def should_compress(content_type, accept_encoding):
    return content_type in compressible_types and "gzip" in accept_encoding


def post_name(filename):
    name, dotext = os.path.splitext(filename)
    a = set(glob(resolve(name) + "*"))
    b = set(glob(resolve("*" + dotext)))
    files = a & b
    return f"{name}({len(files)}){dotext}"
