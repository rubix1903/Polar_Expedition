"""Mission readiness scoring and the mission-control dashboard."""
from .. import db, entities
from ..config import THRESHOLDS as T

def level_for(score):
    return "green" if score >= T["readiness_green"] else "amber" if score >= T["readiness_amber"] else "red"

def resolve_mission(conn, mission_id=None):
    if mission_id:
        return entities.get_row(conn, "missions", int(mission_id))
    return db.one(conn, "select * from missions order by (status='Active') desc, id limit 1")

def share(good, total):
    return 100.0 if not total else round(good / total * 100, 1)

def dimensions(conn, mission_id):
    """Six readiness dimensions, each scored 0-100. Formulas are documented in docs/ARCHITECTURE.md."""
    people = entities.list_rows(conn, "personnel", {"mission_id": mission_id})
    cargo = entities.list_rows(conn, "cargo", {"mission_id": mission_id})
    transports = entities.list_rows(conn, "transports", {"mission_id": mission_id})
    assets = entities.list_rows(conn, "assets")
    incidents = [i for i in entities.list_rows(conn, "incidents", {"mission_id": mission_id}) if i["status"] != "Closed"]
    cleared = sum(1 for p in people if p["medical_cleared"] and p["training_cleared"] and p["permit_cleared"])
    green = sum(1 for c in cargo if c["risk"] == "green")
    amber = sum(1 for c in cargo if c["risk"] == "amber")
    healthy_assets = sum(1 for a in assets if not a["needs_attention"])
    healthy_transport = sum(1 for t in transports if t["status"] not in ("Delayed", "Cancelled") and not t["over_capacity"])
    docs = sum(1 for c in cargo if c["docs_complete"]) + sum(1 for p in people if p["permit_cleared"])
    penalty = sum(T["incident_penalty"].get(i["severity"], 0) for i in incidents)
    dims = [
        ("People", share(cleared, len(people)), f"{cleared} of {len(people)} fully cleared"),
        ("Cargo", share(green + amber / 2, len(cargo)), f"{green} green, {amber} amber of {len(cargo)}"),
        ("Assets", share(healthy_assets, len(assets)), f"{healthy_assets} of {len(assets)} need no attention"),
        ("Transport", share(healthy_transport, len(transports)), f"{healthy_transport} of {len(transports)} on schedule and within capacity"),
        ("Compliance", share(docs, len(cargo) + len(people)), "Cargo documents and personnel permits"),
        ("Emergencies", max(0.0, 100.0 - penalty), f"{len(incidents)} open incidents"),
    ]
    return [{"name": n, "score": s, "level": level_for(s), "detail": d} for n, s, d in dims]

def alerts_for(conn, mission_id):
    out = []
    for c in entities.list_rows(conn, "cargo", {"mission_id": mission_id}):
        if c["risk"] != "green":
            out.append({"level": "critical" if c["risk"] == "red" else "warning", "area": "Cargo", "route": "cargo", "text": f"{c['code']} {c['description'][:50]}: {c['risk_reasons'][0]}"})
    for t in entities.list_rows(conn, "transports", {"mission_id": mission_id}):
        if t["status"] in ("Delayed", "Cancelled"):
            out.append({"level": "critical" if t["status"] == "Cancelled" else "warning", "area": "Transport", "route": "missions", "text": f"{t['name']} is {t['status'].lower()}"})
    for i in entities.list_rows(conn, "incidents", {"mission_id": mission_id}):
        if i["status"] != "Closed":
            out.append({"level": "critical" if i["severity"] in ("High", "Critical") else "warning", "area": "Emergency", "route": "emergency", "text": f"{i['station']}: {i['title']} ({i['severity']}, {i['status']})"})
    for a in entities.list_rows(conn, "assets"):
        if a["needs_attention"]:
            out.append({"level": "critical" if a["status"] == "Maintenance" or a["condition"] == "Poor" else "warning", "area": "Assets", "route": "stock", "text": f"{a['station']}: {a['name']} ({a['tag']}) needs attention"})
    for i in entities.list_rows(conn, "items"):
        if i["level"] != "ok":
            out.append({"level": "critical" if i["level"] == "critical" else "warning", "area": "Inventory", "route": "stock", "text": f"{i['station']}: {i['name']} has {i['cover_days']} days of cover"})
        elif i["days_to_expiry"] is not None and i["days_to_expiry"] < T["expiry_warn_days"]:
            out.append({"level": "warning", "area": "Inventory", "route": "stock", "text": f"{i['station']}: {i['name']} expires in {i['days_to_expiry']} days"})
    out.sort(key=lambda a: a["level"] != "critical")
    return out

def station_map(conn, mission_id):
    people = entities.list_rows(conn, "personnel", {"mission_id": mission_id})
    cargo = entities.list_rows(conn, "cargo", {"mission_id": mission_id})
    incidents = [i for i in entities.list_rows(conn, "incidents", {"mission_id": mission_id}) if i["status"] != "Closed"]
    out = []
    for s in entities.list_rows(conn, "stations"):
        inc = [i for i in incidents if i["station_id"] == s["id"]]
        red = sum(1 for c in cargo if c["station_id"] == s["id"] and c["risk"] == "red")
        health = "critical" if any(i["severity"] in ("High", "Critical") for i in inc) else "warning" if inc or red else "ok"
        out.append({**s, "health": health, "people": sum(1 for p in people if p["station_id"] == s["id"]), "open_incidents": len(inc), "red_cargo": red})
    return out

def dashboard(conn, user, q, body):
    mission = resolve_mission(conn, q.get("mission_id"))
    if not mission:
        raise LookupError("No expedition exists yet")
    mid = mission["id"]
    dims = dimensions(conn, mid)
    cargo = entities.list_rows(conn, "cargo", {"mission_id": mid})
    people = entities.list_rows(conn, "personnel", {"mission_id": mid})
    deadlines = [{"id": t["id"], "name": t["name"], "cutoff": t["cutoff"], "days": t["days_to_cutoff"], "depart": t["depart"], "status": t["status"],
                  "unpacked": sum(1 for c in cargo if c["transport_id"] == t["id"] and c["status"] == "Registered")}
                 for t in entities.list_rows(conn, "transports", {"mission_id": mid}) if t["status"] not in ("Completed", "Cancelled") and t["cutoff"]]
    deadlines.sort(key=lambda d: d["cutoff"])
    return {"mission": mission, "readiness": {"overall": round(sum(d["score"] for d in dims) / len(dims), 1), "dimensions": dims},
            "cargo_by_status": {s: sum(1 for c in cargo if c["status"] == s) for s in ("Registered", "Packed", "In Transit", "Received", "Delivered")},
            "cargo_by_risk": {r: sum(1 for c in cargo if c["risk"] == r) for r in ("green", "amber", "red")},
            "people_by_movement": {m: sum(1 for p in people if p["movement_status"] == m) for m in ("Deployed", "In transit", "At station", "Transferred", "Returning")},
            "deadlines": deadlines, "alerts": alerts_for(conn, mid), "stations": station_map(conn, mid)}
