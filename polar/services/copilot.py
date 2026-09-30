#Operational query assistant.
from .. import entities
from ..config import THRESHOLDS as T
from . import readiness

SUGGESTIONS = ["Which cargo is at risk?", "Which critical assets need attention?", "Which stock will run out first?",
               "Where are our people right now?", "Are there open incidents?", "What is the mission readiness?",
               "What deadlines are coming up?", "Which vessels or flights are delayed?"]

def table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": rows}

def cargo_at_risk(conn, mid, text):
    rows = [c for c in entities.list_rows(conn, "cargo", {"mission_id": mid}) if c["risk"] != "green"]
    rows.sort(key=lambda c: c["risk"] != "red")
    red = sum(1 for c in rows if c["risk"] == "red")
    answer = f"{len(rows)} consignments need attention: {red} red and {len(rows) - red} amber." if rows else "No cargo is at risk right now."
    return answer, [table("Cargo at risk", ["Code", "Description", "Risk", "Main reason"], [[c["code"], c["description"], c["risk"], c["risk_reasons"][0]] for c in rows])] if rows else []

def assets_attention(conn, mid, text):
    rows = [a for a in entities.list_rows(conn, "assets") if a["needs_attention"]]
    answer = f"{len(rows)} assets need attention." if rows else "All assets are in service and within maintenance limits."
    return answer, [table("Assets needing attention", ["Tag", "Asset", "Station", "Status", "Condition", "Hours to service"], [[a["tag"], a["name"], a["station"], a["status"], a["condition"], a["service_hours"]] for a in rows])] if rows else []

def stock_risk(conn, mid, text):
    items = entities.list_rows(conn, "items")
    low = sorted([i for i in items if i["level"] != "ok"], key=lambda i: i["cover_days"])
    expiring = [i for i in items if i["days_to_expiry"] is not None and i["days_to_expiry"] < T["expiry_warn_days"]]
    answer = f"{len(low)} stock lines are below the cover thresholds and {len(expiring)} expire within {T['expiry_warn_days']} days."
    return answer, [table("Low cover", ["Station", "Item", "Cover (days)", "Level"], [[i["station"], i["name"], i["cover_days"], i["level"]] for i in low]),
                    table("Expiring soon", ["Station", "Item", "Days to expiry"], [[i["station"], i["name"], i["days_to_expiry"]] for i in expiring])]

def people_status(conn, mid, text):
    people = entities.list_rows(conn, "personnel", {"mission_id": mid})
    stations = entities.list_rows(conn, "stations")
    match = next((s for s in stations if s["name"].lower() in text or s["code"].lower() in text), None)
    if match:
        people = [p for p in people if p["station_id"] == match["id"]]
    counts = {}
    for p in people:
        counts[p["movement_status"]] = counts.get(p["movement_status"], 0) + 1
    answer = f"{len(people)} personnel" + (f" at {match['name']}" if match else "") + ": " + ", ".join(f"{n} {k.lower()}" for k, n in counts.items()) + "." if people else "No personnel match."
    return answer, [table("Personnel", ["Name", "Role", "Station", "Movement", "Fully cleared"],
                          [[p["name"], p["role"], next((s["name"] for s in stations if s["id"] == p["station_id"]), "-"), p["movement_status"], "Yes" if p["medical_cleared"] and p["training_cleared"] and p["permit_cleared"] else "No"] for p in people])]

def incidents(conn, mid, text):
    rows = [i for i in entities.list_rows(conn, "incidents", {"mission_id": mid}) if i["status"] != "Closed"]
    answer = f"{len(rows)} open incidents." if rows else "There are no open incidents."
    return answer, [table("Open incidents", ["Title", "Station", "Severity", "Status", "People affected", "Pending actions"], [[i["title"], i["station"], i["severity"], i["status"], i["people_count"], i["pending_actions"]] for i in rows])] if rows else []

def readiness_answer(conn, mid, text):
    dims = readiness.dimensions(conn, mid)
    overall = round(sum(d["score"] for d in dims) / len(dims), 1)
    weakest = min(dims, key=lambda d: d["score"])
    return f"Overall readiness is {overall}%. The weakest area is {weakest['name']} at {weakest['score']}%.", [table("Readiness", ["Area", "Score", "Level", "Detail"], [[d["name"], d["score"], d["level"], d["detail"]] for d in dims])]

def deadlines(conn, mid, text):
    rows = [t for t in entities.list_rows(conn, "transports", {"mission_id": mid}) if t["status"] not in ("Completed", "Cancelled") and t["cutoff"]]
    rows.sort(key=lambda t: t["cutoff"])
    answer = f"Next cargo cut-off: {rows[0]['name']} in {rows[0]['days_to_cutoff']} days." if rows else "No upcoming cut-offs."
    return answer, [table("Cargo cut-offs", ["Transport", "Cut-off", "Days", "Status", "Cargo booked"], [[t["name"], t["cutoff"], t["days_to_cutoff"], t["status"], t["cargo_count"]] for t in rows])] if rows else []

def transports(conn, mid, text):
    rows = entities.list_rows(conn, "transports", {"mission_id": mid})
    bad = [t for t in rows if t["status"] in ("Delayed", "Cancelled") or t["over_capacity"]]
    answer = f"{len(bad)} of {len(rows)} transports have problems." if bad else "All transports are on schedule and within capacity."
    return answer, [table("Transports", ["Name", "Status", "Departure", "Load (t)", "Capacity (t)"], [[t["name"], t["status"], t["depart"], t["load_t"], t["cargo_capacity_t"]] for t in (bad or rows)])]

# Ordered: the first intent whose keyword groups all match wins.
INTENTS = [
    (("incident|emergency|casualty|injur",), incidents),
    (("readiness|ready|prepared",), readiness_answer),
    (("deadline|cut-off|cutoff|due date|upcoming",), deadlines),
    (("cargo|consignment|shipment|package",), cargo_at_risk),
    (("asset|equipment|generator|vehicle|maintenance|machine",), assets_attention),
    (("stock|inventory|suppl|fuel|food|expir|run out",), stock_risk),
    (("vessel|ship|flight|aircraft|transport|delay|schedule",), transports),
    (("people|personnel|who|staff|crew|team|where",), people_status),
]

def ask(conn, user, q, body):
    import re
    text = (body.get("question") or "").strip().lower()
    if not text:
        raise ValueError("Ask a question first")
    mission = readiness.resolve_mission(conn, body.get("mission_id"))
    for groups, handler in INTENTS:
        if all(re.search(g, text) for g in groups):
            answer, tables = handler(conn, mission["id"], text)
            return {"intent": handler.__name__, "answer": answer, "tables": tables}
    return {"intent": "help", "answer": "I can answer questions about cargo, assets, stock, personnel, incidents, deadlines, transport and readiness. Try one of the suggestions.", "tables": []}

def suggestions(conn, user, q, body):
    return SUGGESTIONS
