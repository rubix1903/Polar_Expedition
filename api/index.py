#Vercel entry point. vercel.json rewrites every /api/* request to this WSGI application
from http import HTTPStatus

from polar import web

def app(environ, start_response):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(length) if length else b""
    status, content_type, payload = web.handle(environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/"), environ.get("QUERY_STRING", ""),
                                               environ.get("HTTP_AUTHORIZATION", ""), raw)
    start_response(f"{status} {HTTPStatus(status).phrase}", [("Content-Type", content_type), ("Content-Length", str(len(payload)))])
    return [payload]
