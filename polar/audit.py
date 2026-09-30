#Append-only audit trail. Every state change in the system is recorded here.
import time
from . import db

def log(conn, user, action, entity=None, entity_id=None, detail=""):
    actor = user["username"] if user else "system"
    db.insert(conn, "audit", {"ts": int(time.time()), "actor": actor, "action": action, "entity": entity, "entity_id": entity_id, "detail": detail})

def recent(conn, q):
    limit = min(int(q.get("limit", 100)), 500)
    if q.get("entity"):
        return db.rows(conn, "select * from audit where entity=? order by id desc limit ?", (q["entity"], limit))
    return db.rows(conn, "select * from audit order by id desc limit ?", (limit,))
