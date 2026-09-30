#Password hashing, sessions and role checks (standard library only).
import hashlib
import hmac
import os
import secrets
import time
from . import db
from .config import ROLES, SESSION_HOURS

def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"

def verify_password(password, stored):
    salt, digest = stored.split("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$")[1], digest)

def public(user):
    return {k: user[k] for k in ("id", "username", "name", "role")}

def login(conn, username, password):
    user = db.one(conn, "select * from users where username=?", (username,))
    if not user or not verify_password(password or "", user["pw_hash"]):
        raise PermissionError("Invalid username or password")
    token = secrets.token_urlsafe(32)
    db.insert(conn, "sessions", {"token": token, "user_id": user["id"], "expires": int(time.time()) + SESSION_HOURS * 3600})
    return token, public(user)

def user_for(conn, token):
    if not token:
        return None
    row = db.one(conn, "select u.* from sessions s join users u on u.id=s.user_id where s.token=? and s.expires>?", (token, int(time.time())))
    return public(row) if row else None

def logout(conn, token):
    conn.execute("delete from sessions where token=?", (token,))

def can(user, permission):
    perms = ROLES.get(user["role"], set())
    return "*" in perms or permission in perms

def require(user, permission):
    if not can(user, permission):
        raise PermissionError(f"Your role ({user['role']}) does not allow this action")
