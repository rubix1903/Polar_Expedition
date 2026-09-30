#Framework-neutral request handling, shared by the local server and the Vercel function.
import io
import json
import re
import traceback
from contextlib import closing
from urllib.parse import parse_qs

import psycopg

from . import db, routes, security

QR_PATTERN = re.compile(r"^/api/qr/([A-Z0-9-]{4,32})\.svg$")

def qr_svg(code):
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(code, error="m").save(buf, kind="svg", scale=5, border=2, dark="#14293f")
    return buf.getvalue()

def handle(method, path, query_string, authorization, raw_body):
    #Process one API request and return (status, content_type, payload_bytes).
    def reply(status, body, content_type="application/json"):
        return status, content_type, body if isinstance(body, bytes) else json.dumps(body).encode()

    qr = QR_PATTERN.match(path)
    if qr:
        svg = qr_svg(qr[1])
        return reply(200, svg, "image/svg+xml") if svg else reply(501, {"error": "Install segno to generate QR codes"})
    if not path.startswith("/api/"):
        return reply(404, {"error": "Not found"})
    query = {k: v[0] for k, v in parse_qs(query_string).items()}
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        body = json.loads(raw_body) if raw_body else {}
        with closing(db.connect()) as conn:
            if method == "POST" and path == "/api/login":
                new_token, user = security.login(conn, body.get("username"), body.get("password"))
                conn.commit()
                return reply(200, {"token": new_token, "user": user})
            user = security.user_for(conn, token)
            if not user:
                return reply(401, {"error": "Please sign in"})
            if method == "POST" and path == "/api/logout":
                security.logout(conn, token)
                conn.commit()
                return reply(200, {"ok": True})
            try:
                result = routes.dispatch(conn, user, method, path, query, body)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return reply(201 if method == "POST" else 200, result)
    except PermissionError as e:
        return reply(403, {"error": str(e)})
    except LookupError as e:
        return reply(404, {"error": str(e).strip("'\"")})
    except psycopg.IntegrityError:
        return reply(400, {"error": "Record conflicts with existing data or is still referenced elsewhere"})
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, psycopg.DataError) as e:
        return reply(400, {"error": str(e).strip("'\"") or "Invalid request"})
    except Exception:
        traceback.print_exc()  # appears in the Vercel function logs
        return reply(500, {"error": "Server error. Check the deployment logs."})
