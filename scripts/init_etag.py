import os
import sys
import csv
import uuid
from glob import glob
from time import strftime, localtime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpserver import config

header = ["E-Tag", "resource", "last modified"]


def modification_time(path):
    t = os.path.getmtime(path)
    return strftime("%a, %d %b %Y %H:%M:%S %Z", localtime(t))


rows = []
for path in glob(os.path.join(config.ROOT, "**"), recursive=True):
    if os.path.isfile(path):
        resource = os.path.relpath(path, config.ROOT).replace(os.sep, "/")
        rows.append([uuid.uuid1(), resource, modification_time(path)])

os.makedirs(config.VAR_DIR, exist_ok=True)
with open(config.ETAG_CSV, "w", encoding="UTF8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)
