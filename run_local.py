"""Local development server. Serves public/ and the API using the same code as the Vercel deployment.
Run with `python3 run_local.py` after setting DATABASE_URL (in a .env file or the environment).
"""
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from polar import web
from polar.config import STATIC_DIR

class Handler(BaseHTTPRequestHandler):
    def send(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_request(self, method):
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            return self.send(*web.handle(method, url.path, url.query, self.headers.get("Authorization") or "", raw))
        name = "index.html" if url.path == "/" else os.path.basename(url.path)
        full = os.path.join(STATIC_DIR, name)
        if os.path.splitext(name)[1] not in (".html", ".js", ".css") or not os.path.isfile(full):
            return self.send(404, "text/plain", b"Not found")
        self.send(200, mimetypes.guess_type(full)[0] or "application/octet-stream", open(full, "rb").read())

    def do_GET(self): self.handle_request("GET")
    def do_POST(self): self.handle_request("POST")
    def do_PATCH(self): self.handle_request("PATCH")
    def do_DELETE(self): self.handle_request("DELETE")
    def log_message(self, *args): pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Polar Mission Control running at http://localhost:{port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
