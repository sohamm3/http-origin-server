import os

# Authentication for the DELETE method. Overridable via environment.
USERNAME = os.environ.get("HTTP_AUTH_USER", "soham")
PASSWORD = os.environ.get("HTTP_AUTH_PASS", "Soham@2020")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Served document root and runtime-data directory.
ROOT = os.path.join(BASE_DIR, "www")
VAR_DIR = os.path.join(BASE_DIR, "var")

ETAG_CSV = os.path.join(VAR_DIR, "etag.csv")
COOKIES_FILE = os.path.join(VAR_DIR, "cookies.txt")
LOG_FILES = {
    0: os.path.join(VAR_DIR, "user.log"),
    1: os.path.join(VAR_DIR, "debug.log"),
    2: os.path.join(VAR_DIR, "developer.log"),
}

# time after which log files should be compressed (12 hours)
EXPIRES = 43200

MAX_REQUESTS = 20
MAX_URI = 50
MAX_PAYLOAD = 512000

MOVED = os.path.join(ROOT, "old.html")
NEW = os.path.join(ROOT, "new.html")

# Server bind host and the port assigned at startup.
ip = "127.0.0.1"
port = None
