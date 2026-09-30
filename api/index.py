# Vercel entry point: a WSGI application that receives every /api/* request.

from http import HTTPStatus
from urllib.parse import parse_qsl, urlencode

from polar import web

def original_request(environ):
    #Return (path, query_string) as the browser sent them.
    pairs = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    path = next((v for k, v in pairs if k == "__vpath"), None) or environ.get("PATH_INFO", "/")
    if not path.startswith("/"):
        path = "/" + path
    return path, urlencode([(k, v) for k, v in pairs if k != "__vpath"])

def app(environ, start_response):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(length) if length else b""
    path, query = original_request(environ)
    status, content_type, payload = web.handle(environ["REQUEST_METHOD"], path, query, environ.get("HTTP_AUTHORIZATION", ""), raw)
    start_response(f"{status} {HTTPStatus(status).phrase}", [("Content-Type", content_type), ("Content-Length", str(len(payload)))])
    return [payload]