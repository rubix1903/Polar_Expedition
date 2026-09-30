#Central configuration: paths, enumerations, thresholds and role permissions.
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(ROOT, "data", "seed.json")
STATIC_DIR = os.path.join(ROOT, "public")
SESSION_HOURS = 12

def load_env_file():
    """Reads KEY=value lines from .env (local development only). Real environment variables win."""
    path = os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))

load_env_file()

# Enumerations are served to the UI through /api/meta, so dropdowns never duplicate these lists.
ENUMS = {
    "mission_status": ["Planning", "Active", "Completed"],
    "station_status": ["Operational", "Limited", "Closed"],
    "transport_mode": ["Vessel", "Aircraft"],
    "transport_status": ["Scheduled", "In transit", "Delayed", "Completed", "Cancelled"],
    "cargo_status": ["Registered", "Packed", "In Transit", "Received", "Delivered"],
    "cargo_category": ["Scientific equipment", "Food and provisions", "Fuel", "Medical", "Spares",
                       "Shelter and clothing", "Communication", "Hazardous materials"],
    "priority": ["Critical", "High", "Normal"],
    "movement": ["Deployed", "In transit", "At station", "Transferred", "Returning"],
    "asset_status": ["Ready", "In use", "Maintenance"],
    "condition": ["Good", "Fair", "Poor"],
    "criticality": ["High", "Medium", "Low"],
    "incident_type": ["Medical", "Fire", "Equipment failure", "Weather", "Missing person", "Environmental", "Other"],
    "severity": ["Low", "Moderate", "High", "Critical"],
    "incident_status": ["Open", "Responding", "Contained", "Closed"],
    "action_status": ["Pending", "In progress", "Done"],
}

THRESHOLDS = {
    "cutoff_amber_days": 7,      # cargo not packed this close to cut-off turns amber
    "cutoff_red_days": 2,        # ... and red inside this window
    "docs_red_days": 3,          # incomplete paperwork turns red inside this window
    "cover_critical_days": 30,   # stock cover below this is critical
    "cover_low_days": 90,
    "expiry_warn_days": 90,
    "service_due_hours": 25,
    "no_replacement_days": 180,  # assumed gap when a cancelled transport has no replacement
    "readiness_green": 80,
    "readiness_amber": 60,
    "incident_penalty": {"Low": 5, "Moderate": 10, "High": 20, "Critical": 35},
}

# Permission model: a role is a set of permissions; "*" grants everything.
ROLES = {
    "director": {"*"},
    "logistics": {"read", "logistics", "scenario", "copilot"},
    "station_lead": {"read", "people", "incident", "copilot"},
    "viewer": {"read", "copilot"},
}
