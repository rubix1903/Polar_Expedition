#Emergency response: incidents, affected personnel, response actions and closure rules.
import time
from .. import audit, db, entities
from ..config import ENUMS
from ..entities import ENRICH

def enrich_incidents(conn, rows):
    stations = {s["id"]: s["name"] for s in db.rows(conn, "select id, name from stations")}
    people = {r["incident_id"]: r["n"] for r in db.rows(conn, "select incident_id, count(*) n from incident_people group by incident_id")}
    pending = {r["incident_id"]: r["n"] for r in db.rows(conn, "select incident_id, count(*) n from incident_actions where status != 'Done' group by incident_id")}
    for r in rows:
        r.update(station=stations.get(r["station_id"]), people_count=people.get(r["id"], 0), pending_actions=pending.get(r["id"], 0))
    return rows

def create(conn, user, q, body):
    values = entities.clean("incidents", body)
    values.update(reported_at=int(time.time()), reporter=values.get("reporter") or user["name"])
    incident_id = db.insert(conn, "incidents", values)
    for pid in body.get("personnel_ids") or []:
        conn.execute("insert into incident_people(incident_id, personnel_id) values(?, ?) on conflict do nothing", (incident_id, int(pid)))
    audit.log(conn, user, "reported", "incidents", incident_id, f"{values['severity']}: {values['title']}")
    return {"id": incident_id}

def detail(conn, user, q, body, incident_id):
    incident = entities.get_row(conn, "incidents", int(incident_id))
    incident["people"] = db.rows(conn, "select p.id, p.name, p.role, p.contact from incident_people ip join personnel p on p.id=ip.personnel_id where ip.incident_id=?", (incident_id,))
    incident["actions"] = db.rows(conn, "select * from incident_actions where incident_id=? order by id", (incident_id,))
    return incident

def add_action(conn, user, q, body, incident_id):
    entities.get_row(conn, "incidents", int(incident_id))
    if not (body.get("action") or "").strip():
        raise ValueError("Action description is required")
    action_id = db.insert(conn, "incident_actions", {"incident_id": incident_id, "ts": int(time.time()), "action": body["action"].strip(), "assignee": body.get("assignee")})
    audit.log(conn, user, "action added", "incidents", int(incident_id), body["action"][:80])
    return {"id": action_id}

def set_action_status(conn, user, q, body, incident_id, action_id):
    if body.get("status") not in ENUMS["action_status"]:
        raise ValueError("Invalid action status")
    conn.execute("update incident_actions set status=? where id=? and incident_id=?", (body["status"], action_id, incident_id))
    audit.log(conn, user, "action " + body["status"].lower(), "incidents", int(incident_id), f"action {action_id}")
    return {"ok": True}

def set_status(conn, user, q, body, incident_id):
    incident = entities.get_row(conn, "incidents", int(incident_id))
    status = body.get("status")
    if status not in ENUMS["incident_status"]:
        raise ValueError("Invalid incident status")
    if status == "Closed" and incident["pending_actions"]:
        raise ValueError(f"{incident['pending_actions']} response actions are still open")
    conn.execute("update incidents set status=?, closed_at=? where id=?", (status, int(time.time()) if status == "Closed" else None, incident_id))
    audit.log(conn, user, "status", "incidents", int(incident_id), f"{incident['status']} -> {status}")
    return {"status": status}

ENRICH["incidents"] = enrich_incidents
