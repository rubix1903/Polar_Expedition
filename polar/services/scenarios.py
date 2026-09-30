# What-if contingency simulations. Scenarios only read data; nothing is modified.
from .. import audit, entities
from ..config import THRESHOLDS as T
from .inventory import days_until

TYPES = [
    {"id": "transport_delay", "label": "Vessel or flight delay", "target": "transports", "params": [{"k": "days", "l": "Delay (days)", "default": 7}]},
    {"id": "transport_cancel", "label": "Vessel or flight cancellation", "target": "transports", "params": []},
    {"id": "cargo_loss", "label": "Cargo loss", "target": "cargo", "params": []},
    {"id": "evacuation", "label": "Station evacuation", "target": "stations", "params": []},
]

def types(conn, user, q, body):
    return TYPES

def _supply_gap(conn, transport, delay_days):
    #Items at the destination that would run out before the delayed transport arrives.#
    arrival = days_until(transport["arrive"]) or 0
    horizon = max(arrival, 0) + delay_days
    rows = []
    for i in entities.list_rows(conn, "items", {"station_id": transport["station_id"]}):
        if i["cover_days"] is not None and i["cover_days"] < horizon:
            rows.append([i["name"], i["criticality"], i["cover_days"], horizon, round(horizon - i["cover_days"], 1)])
    rows.sort(key=lambda r: -r[4])
    return rows, horizon

def _delay(conn, transport, delay_days, cancelled):
    cargo = [c for c in entities.list_rows(conn, "cargo", {"transport_id": transport["id"]}) if c["status"] not in ("Received", "Delivered")]
    people = entities.list_rows(conn, "personnel", {"transport_id": transport["id"]})
    summary = [f"{len(cargo)} consignments ({sum(c['weight_kg'] or 0 for c in cargo) / 1000:.1f} t) and {len(people)} personnel are booked on {transport['name']}."]
    gap, horizon = _supply_gap(conn, transport, delay_days)
    if cancelled:
        summary.append(f"Assumed {delay_days} days until the next transport reaches {transport['station'] or 'the destination'}.")
    summary.append(f"{len(gap)} stock lines at {transport['station'] or 'the destination'} would run out within the {horizon}-day window." if gap else "Destination stock covers the whole window.")
    return {"summary": summary, "tables": [
        {"title": "Affected cargo", "columns": ["Code", "Description", "Priority", "Hazardous"], "rows": [[c["code"], c["description"], c["priority"], "Yes" if c["hazard"] else "No"] for c in cargo]},
        {"title": "Affected personnel", "columns": ["Name", "Role", "Movement"], "rows": [[p["name"], p["role"], p["movement_status"]] for p in people]},
        {"title": "Stock that runs out before resupply", "columns": ["Item", "Criticality", "Cover (days)", "Needed (days)", "Shortfall (days)"], "rows": gap}]}

def transport_scenario(conn, body, cancelled):
    t = entities.get_row(conn, "transports", int(body["target_id"]))
    if cancelled:
        later = [x for x in entities.list_rows(conn, "transports", {"station_id": t["station_id"]})
                 if x["id"] != t["id"] and x["status"] not in ("Cancelled", "Completed") and (x["arrive"] or "") > (t["arrive"] or "")]
        days = (days_until(min(later, key=lambda x: x["arrive"])["arrive"]) - (days_until(t["arrive"]) or 0)) if later else T["no_replacement_days"]
    else:
        days = int(float(body.get("days") or 7))
    result = _delay(conn, t, days, cancelled)
    result["title"] = f"{'Cancellation' if cancelled else str(days) + '-day delay'}: {t['name']}"
    return result

def cargo_loss(conn, body):
    c = entities.get_row(conn, "cargo", int(body["target_id"]))
    alts = [t for t in entities.list_rows(conn, "transports", {"station_id": c["station_id"]}) if t["status"] not in ("Cancelled", "Completed") and t["id"] != c["transport_id"]]
    stock = [i for i in entities.list_rows(conn, "items", {"station_id": c["station_id"]}) if i["category"] and c["category"] and i["category"].split()[0].lower() in c["category"].lower()]
    summary = [f"{c['code']} ({c['priority']} priority, {(c['weight_kg'] or 0):g} kg) bound for {c['station']} would be lost."]
    summary.append(f"{len(alts)} alternative transports call at {c['station']}." if alts else "No alternative transport is scheduled for this destination.")
    return {"title": f"Loss of {c['code']}", "summary": summary, "tables": [
        {"title": "Alternative transports", "columns": ["Transport", "Cut-off", "Arrival", "Status"], "rows": [[t["name"], t["cutoff"], t["arrive"], t["status"]] for t in alts]},
        {"title": "Related stock at destination", "columns": ["Item", "Stock", "Cover (days)"], "rows": [[i["name"], f"{i['stock']:g} {i['unit']}", i["cover_days"]] for i in stock]}]}

def evacuation(conn, body):
    s = entities.get_row(conn, "stations", int(body["target_id"]))
    people = [p for p in entities.list_rows(conn, "personnel", {"station_id": s["id"]})]
    calls = [t for t in entities.list_rows(conn, "transports", {"station_id": s["id"]}) if t["status"] not in ("Cancelled", "Completed")]
    booked = {t["id"]: sum(1 for p in entities.list_rows(conn, "personnel", {"transport_id": t["id"]})) for t in calls}
    free = sum(max(0, (t["seats"] or 0) - booked[t["id"]]) for t in calls)
    headcount = max(len(people), int(s["crew"] or 0))
    short = headcount - free
    summary = [f"{headcount} people at {s['name']}; {free} free seats on scheduled transports.",
               f"Seat shortfall of {short}: extra lift or a station-based shelter plan is required." if short > 0 else "Scheduled transports could carry everyone."]
    return {"title": f"Evacuation of {s['name']}", "summary": summary, "tables": [
        {"title": "Transports calling at the station", "columns": ["Transport", "Arrival", "Seats", "Booked", "Free"], "rows": [[t["name"], t["arrive"], t["seats"], booked[t["id"]], max(0, (t["seats"] or 0) - booked[t["id"]])] for t in calls]},
        {"title": "Registered personnel", "columns": ["Name", "Role", "Medical", "Permit"], "rows": [[p["name"], p["role"], "Yes" if p["medical_cleared"] else "No", "Yes" if p["permit_cleared"] else "No"] for p in people]}]}

def run(conn, user, q, body):
    kind = body.get("type")
    if not body.get("target_id"):
        raise ValueError("Choose what the scenario applies to")
    if kind in ("transport_delay", "transport_cancel"):
        result = transport_scenario(conn, body, kind == "transport_cancel")
    elif kind == "cargo_loss":
        result = cargo_loss(conn, body)
    elif kind == "evacuation":
        result = evacuation(conn, body)
    else:
        raise ValueError("Unknown scenario type")
    audit.log(conn, user, "simulated", "scenarios", None, result["title"])
    return result
