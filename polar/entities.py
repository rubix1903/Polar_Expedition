#Entity registry.
from . import audit, db
from .config import ENUMS

def F(key, label, kind="text", req=False, enum=None, ref=None, wide=False, unique=False):
    return {"k": key, "l": label, "t": kind, "req": req, "enum": enum, "ref": ref, "w": wide, "u": unique}

ENTITIES = {
    "missions": {"perm": "mission", "fields": [
        F("code", "Code", req=True, unique=True), F("name", "Expedition", req=True), F("season", "Season"),
        F("status", "Status", "select", enum="mission_status"), F("start_date", "Start date", "date"), F("end_date", "End date", "date"),
        F("description", "Description", wide=True)]},
    "stations": {"perm": "mission", "fields": [
        F("code", "Code", req=True, unique=True), F("name", "Station", req=True), F("region", "Region"), F("type", "Type"),
        F("lat", "Latitude", "number"), F("lon", "Longitude", "number"), F("crew", "Crew on station", "number"),
        F("crew_capacity", "Crew capacity", "number"), F("established", "Established", "number"), F("status", "Status", "select", enum="station_status")]},
    "transports": {"perm": "logistics", "fields": [
        F("mission_id", "Expedition", "select", req=True, ref="missions"), F("name", "Vessel or flight", req=True),
        F("mode", "Mode", "select", req=True, enum="transport_mode"), F("origin", "Departure point"),
        F("station_id", "Destination station", "select", ref="stations"), F("depart", "Departure", "date"), F("arrive", "Arrival", "date"),
        F("cutoff", "Cargo cut-off", "date"), F("status", "Status", "select", enum="transport_status"),
        F("cargo_capacity_t", "Cargo capacity (t)", "number"), F("seats", "Passenger seats", "number")]},
    "cargo": {"perm": "logistics", "custom_create": True, "extra": "code text unique not null, status text not null default 'Registered'", "fields": [
        F("mission_id", "Expedition", "select", req=True, ref="missions"), F("description", "Description", req=True, wide=True),
        F("category", "Category", "select", enum="cargo_category"), F("hazard", "Hazardous", "checkbox"),
        F("weight_kg", "Weight (kg)", "number"), F("volume_m3", "Volume (m3)", "number"), F("origin", "Origin"),
        F("station_id", "Destination station", "select", req=True, ref="stations"), F("transport_id", "Assigned transport", "select", ref="transports"),
        F("priority", "Priority", "select", enum="priority"), F("docs_complete", "Documentation complete", "checkbox"), F("owner", "Owner or team")]},
    "personnel": {"perm": "people", "fields": [
        F("name", "Name", req=True), F("role", "Role", req=True), F("organisation", "Organisation"),
        F("mission_id", "Expedition", "select", ref="missions"), F("station_id", "Station", "select", ref="stations"),
        F("movement_status", "Movement status", "select", enum="movement"), F("transport_id", "Assigned transport", "select", ref="transports"),
        F("medical_cleared", "Medical clearance", "checkbox"), F("training_cleared", "Training clearance", "checkbox"),
        F("permit_cleared", "Permit clearance", "checkbox"), F("contact", "Contact")]},
    "assets": {"perm": "logistics", "fields": [
        F("station_id", "Station", "select", req=True, ref="stations"), F("tag", "Tag", req=True, unique=True), F("name", "Asset", req=True),
        F("category", "Category"), F("model", "Model"), F("serial", "Serial number"), F("status", "Status", "select", enum="asset_status"),
        F("condition", "Condition", "select", enum="condition"), F("service_hours", "Hours to service", "number"),
        F("total_hours", "Total operating hours", "number"), F("commissioned", "Year commissioned", "number")]},
    "items": {"perm": "logistics", "fields": [
        F("station_id", "Station", "select", req=True, ref="stations"), F("name", "Item", req=True), F("category", "Category"),
        F("unit", "Unit", req=True), F("stock", "Stock", "number"), F("daily_rate", "Use per day", "number", req=True),
        F("per_person", "Scales with crew", "checkbox"), F("kg_per_unit", "Weight per unit (kg)", "number"),
        F("unit_cost", "Unit cost (INR)", "number"), F("supplier", "Supplier"), F("location", "Storage location"),
        F("criticality", "Criticality", "select", enum="criticality"), F("expiry", "Expiry date", "date"), F("batch", "Batch")]},
    "incidents": {"perm": "incident", "custom_create": True,
                  "extra": "status text not null default 'Open', reported_at bigint not null default 0, closed_at bigint", "fields": [
        F("mission_id", "Expedition", "select", req=True, ref="missions"), F("station_id", "Station", "select", req=True, ref="stations"),
        F("title", "Title", req=True, wide=True), F("type", "Type", "select", req=True, enum="incident_type"),
        F("severity", "Severity", "select", req=True, enum="severity"), F("description", "Description", wide=True), F("reporter", "Reported by")]},
}

ENRICH = {}  # entity name -> function(conn, rows) that adds computed fields; registered by the services

def ddl():
    statements = []
    for name, entity in ENTITIES.items():
        cols = ["id integer generated by default as identity primary key"]
        for f in entity["fields"]:
            sql_type = "double precision" if f["t"] == "number" else "integer" if f["t"] == "checkbox" or f["ref"] else "text"
            col = f"{f['k']} {sql_type}"
            if f["req"]:
                col += " not null"
            if f["t"] == "checkbox":
                col += " not null default 0"
            if f["u"]:
                col += " unique"
            if f["ref"]:
                col += f" references {f['ref']}(id)"
            cols.append(col)
        if entity.get("extra"):
            cols.append(entity["extra"])
        statements.append(f"create table if not exists {name}({', '.join(cols)})")
    return statements

def clean(name, body, partial=False):
    #Validate and coerce a request body against the entity's field definitions.
    out = {}
    for f in ENTITIES[name]["fields"]:
        k = f["k"]
        if k not in body:
            if not partial and f["req"]:
                raise ValueError(f"{f['l']} is required")
            if not partial and f["enum"] and not f["req"]:
                out[k] = ENUMS[f["enum"]][0]
            continue
        v = body[k]
        if f["t"] == "checkbox":
            out[k] = int(v in (True, 1, "1", "true", "on"))
            continue
        if v is None or v == "":
            if f["req"]:
                raise ValueError(f"{f['l']} is required")
            out[k] = None
            continue
        if f["t"] == "number" or f["ref"]:
            try:
                out[k] = int(v) if f["ref"] else float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{f['l']} must be a number")
            if f["t"] == "number" and out[k] < 0 and k not in ("lat", "lon"):
                raise ValueError(f"{f['l']} cannot be negative")
        else:
            out[k] = str(v).strip()
        if f["enum"] and out[k] not in ENUMS[f["enum"]]:
            raise ValueError(f"{f['l']} must be one of: {', '.join(ENUMS[f['enum']])}")
    return out

def list_rows(conn, name, q=None):
    keys = {f["k"] for f in ENTITIES[name]["fields"]} | {"id"} | ({"status"} if "status" in ENTITIES[name].get("extra", "") else set())
    where, args = [], []
    for k, v in (q or {}).items():
        if k in keys and v != "":
            where.append(f"{k}=?")
            args.append(int(v) if k == "id" or k.endswith("_id") else v)
    sql = f"select * from {name}" + (" where " + " and ".join(where) if where else "") + " order by id"
    rows = db.rows(conn, sql, args)
    return ENRICH[name](conn, rows) if name in ENRICH else rows

def get_row(conn, name, row_id):
    rows = list_rows(conn, name, {"id": row_id})
    if not rows:
        raise LookupError(f"{name[:-1].capitalize()} not found")
    return rows[0]

def label(values, row_id):
    return values.get("name") or values.get("tag") or values.get("code") or values.get("title") or str(row_id)

def create(conn, user, name, body):
    values = clean(name, body)
    row_id = db.insert(conn, name, values)
    audit.log(conn, user, "created", name, row_id, label(values, row_id))
    return {"id": row_id}

def update(conn, user, name, row_id, body):
    get_row(conn, name, row_id)
    values = clean(name, body, partial=True)
    if values:
        conn.execute(f"update {name} set {','.join(k + '=?' for k in values)} where id=?", [*values.values(), row_id])
    audit.log(conn, user, "updated", name, row_id, ", ".join(f"{k}={v}" for k, v in values.items())[:200])
    return {"ok": True}

def delete(conn, user, name, row_id):
    row = get_row(conn, name, row_id)
    conn.execute(f"delete from {name} where id=?", (row_id,))
    audit.log(conn, user, "deleted", name, row_id, label(row, row_id))
    return {"ok": True}
