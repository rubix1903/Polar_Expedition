#API route table. Each handler has the signature handler(conn, user, query, body, *path_args)."""
import re
from . import audit, entities, security
from .config import ENUMS, ROLES, THRESHOLDS
from .services import cargo, copilot, incidents, inventory, readiness, scenarios  # noqa: F401  (registers enrichers)

ROUTES = []
PUBLIC = "public"

def route(method, pattern, perm="read"):
    def register(fn):
        ROUTES.append((method, re.compile(pattern + "$"), perm, fn))
        return fn
    return register

def meta(conn, user, q, body):
    fields = {name: {"perm": e["perm"], "fields": e["fields"], "custom_create": e.get("custom_create", False)} for name, e in entities.ENTITIES.items()}
    perms = sorted({p for r in ROLES.values() for p in r if p != "*"} | {"mission", "logistics", "people", "incident", "scenario", "audit"})
    return {"user": user, "enums": ENUMS, "entities": fields, "thresholds": THRESHOLDS,
            "permissions": [p for p in perms if security.can(user, p)], "cargo_flow": ENUMS["cargo_status"]}

route("GET", "/api/meta")(meta)
route("GET", "/api/dashboard")(readiness.dashboard)
route("GET", "/api/audit", "audit")(lambda conn, user, q, b: audit.recent(conn, q))
route("GET", "/api/copilot/suggestions", "copilot")(copilot.suggestions)
route("POST", "/api/copilot/ask", "copilot")(copilot.ask)
route("GET", "/api/scenarios/types", "scenario")(scenarios.types)
route("POST", "/api/scenarios/run", "scenario")(scenarios.run)
route("POST", "/api/cargo", "logistics")(cargo.register)
route("POST", r"/api/cargo/(\d+)/advance", "logistics")(cargo.advance)
route("GET", r"/api/cargo/(\d+)/custody")(cargo.custody)
route("GET", r"/api/cargo/track/([A-Za-z0-9-]+)")(cargo.track)
route("POST", "/api/incidents", "incident")(incidents.create)
route("GET", r"/api/incidents/(\d+)")(incidents.detail)
route("POST", r"/api/incidents/(\d+)/actions", "incident")(incidents.add_action)
route("PATCH", r"/api/incidents/(\d+)/actions/(\d+)", "incident")(incidents.set_action_status)
route("POST", r"/api/incidents/(\d+)/status", "incident")(incidents.set_status)

def generic(conn, user, method, path, q, body):
    #Generic CRUD for every registered entity. Returns None when the path is not an entity path.
    m = re.fullmatch(r"/api/([a-z]+)(?:/(\d+))?", path)
    if not m or m[1] not in entities.ENTITIES:
        return None
    name, row_id = m[1], m[2]
    if method == "GET":
        return entities.get_row(conn, name, int(row_id)) if row_id else entities.list_rows(conn, name, q)
    security.require(user, entities.ENTITIES[name]["perm"])
    if method == "POST" and not row_id:
        return entities.create(conn, user, name, body)
    if method == "PATCH" and row_id:
        return entities.update(conn, user, name, int(row_id), body)
    if method == "DELETE" and row_id:
        return entities.delete(conn, user, name, int(row_id))
    return None

def dispatch(conn, user, method, path, q, body):
    for m, pattern, perm, fn in ROUTES:
        hit = pattern.match(path)
        if m == method and hit:
            security.require(user, perm)
            args = [int(g) if g.isdigit() else g for g in hit.groups()]  # numeric path segments are record ids
            return fn(conn, user, q, body, *args)
    result = generic(conn, user, method, path, q, body)
    if result is None:
        raise LookupError("Not found")
    return result
