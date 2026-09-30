# Architecture and rules

## Design principles

- **One source of truth.** Enumerations, thresholds and roles live in `polar/config.py`. Field definitions live in `polar/entities.py`.
  The database schema, request validation, generic CRUD and the browser forms are all generated from them, and the client reads
  them from `GET /api/meta`. Nothing is duplicated in JavaScript.
- **Services hold business rules.** Route handlers are thin; rules such as "cargo cannot be packed without documents" live in `app/services/`.
- **Everything is audited.** Every create, update, delete, handover, incident change and simulation writes to the `audit` table.

## Services

| Service | Responsibility |
|---|---|
| `services/cargo.py` | Registration, code generation, custody events, status flow, risk engine, transport load |
| `services/inventory.py` | Days of cover, expiry, stock value, asset service and attention flags |
| `services/incidents.py` | Incident creation with affected people, response actions, closure rules |
| `services/readiness.py` | Six-dimension readiness scoring, alerts, station map data, dashboard |
| `services/scenarios.py` | Read-only what-if simulations |
| `services/copilot.py` | Intent matching and answer generation from live data |
| `security.py` | PBKDF2 password hashing, session tokens, role permissions |

## Cargo risk rules

Status flow: Registered, Packed, In Transit, Received, Delivered. Received and Delivered cargo is always green.
Otherwise the worst applicable level wins, and every triggered reason is shown.

| Condition | Level |
|---|---|
| Transport cancelled | Red |
| Cut-off passed and cargo not packed | Red |
| Cut-off within `cutoff_red_days` (2) and cargo not packed | Red |
| Documents incomplete and cut-off within `docs_red_days` (3) | Red |
| Transport delayed | Amber |
| Transport over cargo capacity | Amber |
| No transport assigned | Amber |
| Cut-off within `cutoff_amber_days` (7) and cargo not packed | Amber |
| Documents incomplete | Amber |
| Hazardous consignment | Amber |

Cargo cannot move from Registered to Packed while documentation is incomplete.

## Readiness formulas (each 0-100; green at 80 or more, amber at 60 or more)

- **People**: fully cleared (medical, training, permit) as a share of personnel.
- **Cargo**: (green + half of amber) as a share of consignments.
- **Assets**: assets needing no attention (not in maintenance, not poor, not due for service) as a share of all assets.
- **Transport**: transports that are not delayed, cancelled or over capacity, as a share of legs.
- **Compliance**: (cargo with complete documents + personnel with permits) as a share of cargo plus personnel.
- **Emergencies**: 100 minus penalties for open incidents (Low 5, Moderate 10, High 20, Critical 35).

Overall readiness is the mean of the six. Thresholds are in `THRESHOLDS`.

## Incident rules

An incident cannot be closed while any response action is not Done. Affected personnel are chosen from the personnel registered at the station.

## What-if scenarios

`POST /api/scenarios/run` with `type` and `target_id`. Types: `transport_delay` (plus `days`), `transport_cancel`, `cargo_loss`, `evacuation`.
Delay and cancellation list affected cargo and people and the destination stock that would run out before the new arrival.
Cancellation assumes the gap to the next transport to that station, or `no_replacement_days` if there is none.
Evacuation compares headcount with free seats on transports calling at the station.

## Offline-first mode

- `sw.js` caches the application shell.
- `app.js` caches every successful GET in `localStorage`; offline, pages show the last saved data with an "Offline mode" banner.
- Writes made offline are queued in `localStorage` and replayed in order when the connection returns (or via "Sync now").
  The server still validates each change; rejected changes are reported and skipped.

## Security notes

- Passwords are salted PBKDF2-SHA256. Sessions are random tokens that expire after `SESSION_HOURS`.
- Every API route except sign-in and QR images requires a valid token; writes check role permissions server-side.
- The QR endpoint only encodes the cargo code text and reveals nothing else.
- Before real deployment: serve over HTTPS, replace demo credentials, and move to a production database.

## API summary

All routes are under `/api` and need `Authorization: Bearer <token>` except `POST /login`.

| Route | Purpose |
|---|---|
| `POST /login`, `POST /logout`, `GET /meta` | Session, enumerations, field definitions, permissions |
| `GET /dashboard?mission_id=` | Readiness, pipeline, deadlines, alerts, station map data |
| `GET/POST /{missions,stations,transports,personnel,assets,items}` and `GET/PATCH/DELETE .../{id}` | Generic CRUD; list endpoints accept field filters such as `?mission_id=1` |
| `GET/POST /cargo`, `GET /cargo/{id}/custody`, `POST /cargo/{id}/advance`, `GET /cargo/track/{code}` | Cargo registration, custody, handover, scan lookup |
| `GET /qr/{code}.svg` (public) | QR label |
| `GET/POST /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/actions`, `PATCH /incidents/{id}/actions/{aid}`, `POST /incidents/{id}/status` | Emergency response |
| `POST /copilot/ask`, `GET /copilot/suggestions` | Operational assistant |
| `GET /scenarios/types`, `POST /scenarios/run` | What-if planner |
| `GET /audit?limit=&entity=` | Audit timeline |

