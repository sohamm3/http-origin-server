status_codes = {
    200: "OK",
    201: "Created",
    204: "No Content",
    301: "Moved Permanently",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    411: "Length Required",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    505: "HTTP Version not Supported",
}

# human-readable detail lines for inline error/status bodies
status_messages = {
    200: "The request succeeded.",
    201: "The resource was created successfully.",
    204: "The request succeeded with no content to return.",
    301: "The resource has moved permanently.",
    304: "The resource has not been modified.",
    400: "The server could not understand the request.",
    401: "Authentication is required to access this resource.",
    403: "You do not have permission to access this resource.",
    404: "The requested resource was not found on this server.",
    405: "The request method is not allowed for this resource.",
    408: "The server timed out waiting for the request.",
    411: "A Content-Length header is required for this request.",
    413: "The request payload is larger than the server allows.",
    414: "The request URI is longer than the server allows.",
    415: "The request media type is not supported.",
    500: "The server encountered an internal error.",
    501: "The request method is not implemented by the server.",
    502: "The server received an invalid response from upstream.",
    503: "The server is currently unable to handle the request.",
    505: "The HTTP version used in the request is not supported.",
}

http_versions = ["HTTP/1.0", "HTTP/1.1"]

mime_types = [
    "text/html",
    "text/css",
    "text/plain",
    "text/csv",
    "application/pdf",
    "application/json",
    "audio/mpeg",
    "image/jpeg",
    "image/png",
    "image/gif",
    "video/mp4",
]

binary_extensions = ["png", "jpg", "jpeg", "mp3", "mp4", "pdf", "gif"]

Allow = ["GET", "HEAD", "DELETE", "PUT", "POST"]

compressible_types = ["text/html", "text/plain", "text/css", "application/json"]
