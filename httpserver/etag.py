import os
import csv

from . import config
from .locks import write_lock
from .fileio import modification_time, resolve

# resource name -> ETag string, loaded once at startup and updated on first
# access of a not-yet-seen file.
_etags = {}


def load_etags():
    _etags.clear()
    if not os.path.isfile(config.ETAG_CSV):
        os.makedirs(config.VAR_DIR, exist_ok=True)
        with open(config.ETAG_CSV, "w", encoding="UTF8", newline="") as f:
            csv.writer(f).writerow(["E-Tag", "resource", "last modified"])
        return
    with open(config.ETAG_CSV, newline="", encoding="UTF8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                _etags[row[1]] = row[0]


def get_etag(file):
    # Derive from mtime+size so the validator changes when the file changes.
    st = os.stat(resolve(file))
    etag = f'"{int(st.st_mtime)}-{st.st_size}"'
    # Record/refresh the row only when the value is new; the lock keeps
    # concurrent appends from interleaving.
    with write_lock:
        if _etags.get(file) != etag:
            _etags[file] = etag
            with open(config.ETAG_CSV, "a+", encoding="UTF8", newline="") as f:
                csv.writer(f).writerow([etag, file, modification_time(file)])
    return etag
