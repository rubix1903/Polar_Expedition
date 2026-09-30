#Cargo registration, chain of custody, deadline intelligence and the cargo risk engine.
import time
from datetime import date
from .. import audit, db, entities
from ..config import ENUMS, THRESHOLDS as T
from ..entities import ENRICH
from .inventory import days_until

FLOW = ENUMS["cargo_status"]
LEVELS = ["green", "amber", "red"]

def transport_loads(conn):
    #Tonnes assigned to each transport, used to detect over-booked vessels and flights.
    rows = db.rows(conn, "select transport_id, sum(weight_kg) kg from cargo where transport_id is not null group by transport_id")
    return {r["transport_id"]: (r["kg"] or 0) / 1000 for r in rows}

def assess(cargo, transport, load_t):
    # Return (level, reasons) for one consignment. See docs/ARCHITECTURE.md for the rule table.#
    if cargo["status"] in ("Received", "Delivered"):
        return "green", []
    level, reasons = 0, []

    def flag(lvl, why):
        nonlocal level
        level = max(level, lvl)
        reasons.append(why)

    days = days_until(transport["cutoff"]) if transport else None
    unpacked = cargo["status"] == "Registered"
    if transport:
        if transport["status"] == "Cancelled":
            flag(2, f"{transport['name']} is cancelled")
        elif transport["status"] == "Delayed":
            flag(1, f"{transport['name']} is delayed")
        if transport["cargo_capacity_t"] and load_t > transport["cargo_capacity_t"]:
            flag(1, f"{transport['name']} is over capacity ({load_t:.1f} t of {transport['cargo_capacity_t']:g} t)")
    else:
        flag(1, "No transport assigned")
    if days is not None and unpacked:
        if days < 0:
            flag(2, f"Cut-off passed {-days} days ago and cargo is not packed")
        elif days <= T["cutoff_red_days"]:
            flag(2, f"Cut-off in {days} days and cargo is not packed")
        elif days <= T["cutoff_amber_days"]:
            flag(1, f"Cut-off in {days} days and cargo is not packed")
    if not cargo["docs_complete"]:
        urgent = days is not None and days <= T["docs_red_days"]
        flag(2 if urgent else 1, "Documentation incomplete")
    if cargo["hazard"]:
        flag(1, "Hazardous consignment needs special handling")
    return LEVELS[level], reasons

def enrich_cargo(conn, rows):
    transports = {t["id"]: t for t in db.rows(conn, "select * from transports")}
    stations = {s["id"]: s["name"] for s in db.rows(conn, "select id, name from stations")}
    loads = transport_loads(conn)
    for r in rows:
        t = transports.get(r["transport_id"])
        level, reasons = assess(r, t, loads.get(r["transport_id"], 0))
        r.update(risk=level, risk_reasons=reasons, transport=t["name"] if t else None, cutoff=t["cutoff"] if t else None,
                 days_to_cutoff=days_until(t["cutoff"]) if t else None, station=stations.get(r["station_id"]))
        r["next_status"] = FLOW[FLOW.index(r["status"]) + 1] if r["status"] != FLOW[-1] else None
    return rows

def enrich_transports(conn, rows):
    loads = transport_loads(conn)
    missions = {m["id"]: m["name"] for m in db.rows(conn, "select id, name from missions")}
    stations = {s["id"]: s["name"] for s in db.rows(conn, "select id, name from stations")}
    counts = {r["transport_id"]: r["n"] for r in db.rows(conn, "select transport_id, count(*) n from cargo where transport_id is not null group by transport_id")}
    for r in rows:
        load = loads.get(r["id"], 0)
        r.update(mission=missions.get(r["mission_id"]), station=stations.get(r["station_id"]), load_t=round(load, 2), cargo_count=counts.get(r["id"], 0),
                 over_capacity=bool(r["cargo_capacity_t"] and load > r["cargo_capacity_t"]), days_to_cutoff=days_until(r["cutoff"]))
    return rows

def next_code(conn):
    n = (db.one(conn, "select coalesce(max(id), 0) + 1 n from cargo") or {"n": 1})["n"]
    return f"CGO-{date.today().year}-{n:04d}"

def add_event(conn, cargo_id, status, location, handler, note="", ts=None):
    db.insert(conn, "custody", {"cargo_id": cargo_id, "ts": ts or int(time.time()), "status": status, "location": location, "handler": handler, "note": note})

def register(conn, user, q, body):
    values = entities.clean("cargo", body)
    values["code"] = next_code(conn)
    cargo_id = db.insert(conn, "cargo", values)
    add_event(conn, cargo_id, "Registered", values.get("origin") or "Origin", user["name"], "Consignment registered")
    audit.log(conn, user, "registered", "cargo", cargo_id, f"{values['code']} {values['description'][:60]}")
    return {"id": cargo_id, "code": values["code"]}

def advance(conn, user, q, body, cargo_id):
    cargo = entities.get_row(conn, "cargo", int(cargo_id))
    if not cargo["next_status"]:
        raise ValueError("Cargo is already delivered")
    if cargo["next_status"] == "Packed" and not cargo["docs_complete"]:
        raise ValueError("Documentation must be complete before cargo can be packed")
    status = cargo["next_status"]
    default_location = {"Packed": cargo["origin"], "In Transit": cargo["transport"]}.get(status, cargo["station"])
    conn.execute("update cargo set status=? where id=?", (status, cargo_id))
    add_event(conn, cargo_id, status, body.get("location") or default_location, body.get("handler") or user["name"], body.get("note") or "")
    audit.log(conn, user, "advanced", "cargo", int(cargo_id), f"{cargo['code']} -> {status}")
    return {"status": status}

def custody(conn, user, q, body, cargo_id):
    return db.rows(conn, "select * from custody where cargo_id=? order by ts, id", (cargo_id,))

def track(conn, user, q, body, code):
    rows = [r for r in entities.list_rows(conn, "cargo") if r["code"] == str(code).upper()]
    if not rows:
        raise LookupError("No cargo with that code")
    return {"cargo": rows[0], "custody": db.rows(conn, "select * from custody where cargo_id=? order by ts, id", (rows[0]["id"],))}

ENRICH["cargo"] = enrich_cargo
ENRICH["transports"] = enrich_transports
