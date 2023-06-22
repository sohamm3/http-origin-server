import os

# For authentication in delete request.
# Overridable via environment; the in-source defaults match the committed test
# Credentials so authentication is coherent out of the box
USERNAME = os.environ.get("HTTP_AUTH_USER", "soham")
PASSWORD = os.environ.get("HTTP_AUTH_PASS", "Soham@2020")

# root directory
ROOT = os.getcwd()

# time after which log files should be compressed(12 hours)
EXPIRES = 43200

# max simultaneous connections
MAX_REQUESTS = 20

# max uri length
MAX_URI = 50

# max payload size (512 KB)
MAX_PAYLOAD = 512000

# request URI which has been moved permanently
MOVED = ROOT + "/old.html"

# redirection to
NEW = ROOT + "/new.html"
