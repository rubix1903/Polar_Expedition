#Loads data/seed.json into an empty database. Day offsets (keys ending in _d) are relative to today.
import json
import time
from datetime import date, timedelta
from . import db
from .config import ENUMS, SEED_PATH
from .security import hash_password
from .services import cargo as cargo_service

REFS = {"mission_id": ("missions", "mission"), "station_id": ("stations", "station"), "transport_id": ("transports", "transport")}

def load(conn):
    if db.one(conn, "select id from users limit 1"):
        return False
    data = json.load(open(SEED_PATH))
    today, now = date.today(), int(time.time())
    ids = {"missions": {}, "stations": {}, "transports": {}, "personnel": {}}

    def resolve(row):
        out = {}
        for k, v in row.items():
            if k.endswith("_d"):
                out[k[:-2]] = (today + timedelta(days=v)).isoformat()
            else:
                out[k] = v
        for column, (table, alias) in REFS.items():
            if alias in out:
                out[column] = ids[table][out.pop(alias)]
        return out

    for u in data["users"]:
        db.insert(conn, "users", {"username": u["username"], "name": u["name"], "role": u["role"], "pw_hash": hash_password(u["password"])})
    for table, key in (("missions", "code"), ("stations", "code"), ("transports", "name"), ("personnel", "name"), ("assets", None)):
        for row in data[table]:
            values = resolve(row)
            new_id = db.insert(conn, table, values)
            if key:
                ids[table][row[key]] = new_id
    transports = {r["id"]: r for r in db.rows(conn, "select * from transports")}
    flow = ENUMS["cargo_status"]
    for row in data["cargo"]:
        values = resolve(row)
        if "mission_id" not in values:
            values["mission_id"] = transports[values["transport_id"]]["mission_id"]
        values["code"] = cargo_service.next_code(conn)
        cargo_id = db.insert(conn, "cargo", values)
        reached = flow.index(values["status"])
        for step, status in enumerate(flow[: reached + 1]):
            place = {"Registered": values["origin"], "Packed": values["origin"]}.get(status, transports.get(values.get("transport_id"), {}).get("name"))
            cargo_service.add_event(conn, cargo_id, status, place, "Seed data", ts=now - (reached - step + 1) * 86400)
    for st in db.rows(conn, "select id, crew from stations"):
        for n, t in enumerate(data["item_templates"]):
            jitter = 0.55 + ((n * 7 + st["id"] * 3) % 10) / 10
            scale = (st["crew"] or 1) / 25
            expiry = None
            if t.get("shelf_days"):
                short = 0.4 if (n + st["id"]) % 5 == 0 else 1
                expiry = (today + timedelta(days=int(t["shelf_days"] * jitter * short))).isoformat()
            db.insert(conn, "items", {"station_id": st["id"], "name": t["name"], "category": t["category"], "unit": t["unit"], "stock": round(t["stock"] * scale * jitter),
                                      "daily_rate": t["daily_rate"] if t["per_person"] else round(t["daily_rate"] * scale, 3), "per_person": t["per_person"],
                                      "kg_per_unit": t["kg_per_unit"], "unit_cost": t["unit_cost"], "supplier": t["supplier"], "location": t["location"],
                                      "criticality": t["criticality"], "expiry": expiry, "batch": f"B{st['id']}{n:02d}-26"})
    for row in data["incidents"]:
        values = resolve({k: v for k, v in row.items() if k not in ("people", "actions", "hours_ago")})
        values["reported_at"] = now - row["hours_ago"] * 3600
        incident_id = db.insert(conn, "incidents", values)
        for name in row["people"]:
            conn.execute("insert into incident_people(incident_id, personnel_id) values(?, ?)", (incident_id, ids["personnel"][name]))
        for a in row["actions"]:
            db.insert(conn, "incident_actions", {"incident_id": incident_id, "ts": values["reported_at"], **a})
    return True
