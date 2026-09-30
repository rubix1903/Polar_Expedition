#Inventory and asset enrichment: days of cover, expiry, service and attention flags.
from datetime import date
from .. import db
from ..config import THRESHOLDS as T
from ..entities import ENRICH

def days_until(iso):
    return (date.fromisoformat(iso) - date.today()).days if iso else None

def enrich_items(conn, rows):
    stations = {s["id"]: s for s in db.rows(conn, "select id, name, crew from stations")}
    for r in rows:
        st = stations.get(r["station_id"], {})
        use = r["daily_rate"] * ((st.get("crew") or 0) if r["per_person"] else 1)
        cover = round(r["stock"] / use, 1) if use else None
        r.update(station=st.get("name"), use_per_day=round(use, 2), cover_days=cover, days_to_expiry=days_until(r["expiry"]),
                 value=round((r["stock"] or 0) * (r["unit_cost"] or 0)))
        r["level"] = ("critical" if cover is not None and cover < T["cover_critical_days"]
                      else "low" if cover is not None and cover < T["cover_low_days"] else "ok")
    return rows

def enrich_assets(conn, rows):
    names = {s["id"]: s["name"] for s in db.rows(conn, "select id, name from stations")}
    for r in rows:
        r["station"] = names.get(r["station_id"])
        r["service_due"] = (r["service_hours"] or 0) < T["service_due_hours"]
        r["needs_attention"] = r["status"] == "Maintenance" or r["condition"] == "Poor" or r["service_due"]
    return rows

ENRICH["items"] = enrich_items
ENRICH["assets"] = enrich_assets
