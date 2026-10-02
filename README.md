# Polar Mission Control

Integrated Polar Expedition Logistics and Asset Management System (SIH26062, Ministry of Earth Sciences).
One platform connecting **people, cargo, assets, movement and emergencies** for a polar expedition.


## Sign in

| User | Role | Can do |
|---|---|---|
| `director` | Mission Director | Everything, including audit and expedition setup |
| `logistics` | Logistics Officer | Cargo, transports, assets, inventory, what-if planner |
| `stationlead` | Station Leader | Personnel movement and emergency response |
| `viewer` | Observer | Read-only, copilot |

All demo passwords are `Polar@2026`.

## What is in the prototype

1. **Mission dashboard**: readiness across six dimensions, Antarctic and Arctic station maps, cargo pipeline, deadline intelligence, alerts.
2. **Expedition creation and timeline**: expeditions, transport legs with cargo cut-offs, stations.
3. **Cargo registration and QR tracking**: generated codes, printable QR labels, scan/lookup, chain of custody, Registered to Delivered flow.
4. **Green, amber and red cargo risk**: rule-based risk engine with the reasons shown on every consignment.
5. **Personnel movement board**: Deployed, In transit, At station, Transferred, Returning, with medical, training and permit clearances.
6. **Asset and inventory registry**: condition, maintenance hours, stock cover, expiry and value.
7. **Emergency response centre**: incidents, affected personnel, assigned response actions, closure rules.
8. **Expedition copilot**: plain-language operational questions answered from live data.
9. **Role-based access and audit timeline**: four roles. every change logged.
10. **Differentiators**: offline-first mode with a sync queue, what-if contingency planner, mission readiness view, chain of custody.

## Project layout

```
api/index.py         Vercel entry point (WSGI)
run_local.py         local development server
polar/web.py         request handling shared by both, authentication, error mapping
polar/seed_once.py   creates tables and loads sample data
polar/config.py        enumerations, thresholds, roles (the only place these live)
polar/entities.py      field definitions: schema, validation, generic CRUD and UI forms
polar/db.py            SQLite helpers
polar/security.py      password hashing, sessions, permission checks
polar/audit.py         append-only audit trail
polar/routes.py        route table
polar/seed.py          loads data/seed.json
polar/services/        cargo, inventory, incidents, readiness, scenarios, copilot
data/seed.json       sample data (dates are offsets from today)
public/              web client (index.html, app.js, style.css, sw.js)
docs/ARCHITECTURE.md rules, formulas, API and design notes
```

## Honest limitations

- The station map is a graticule with station markers, not a coastline map, so it works fully offline.
- The copilot is a deterministic intent matcher, not a language model. It only reports what is in the database.
- Offline mode queues changes made in the browser and syncs them when the connection returns; there is no conflict resolution beyond last write wins.
- Sample vessels, suppliers, people and stock levels are invented for demonstration.
