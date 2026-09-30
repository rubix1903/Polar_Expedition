"use strict";
//Polar Mission Control web client.
const $ = (sel, root = document) => root.querySelector(sel);
const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = v => v === null || v === undefined || v === "" ? "-" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 1 });
const inr = v => "\u20b9" + Number(v || 0).toLocaleString("en-IN");
const fmtDate = v => v ? new Date(v.length === 10 ? v + "T00:00" : v).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "-";
const fmtTime = ts => new Date(ts * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const TONE = { green: "ok", amber: "low", red: "critical", ok: "ok", low: "low", critical: "critical", warning: "low", Ready: "ok", "In use": "info", Maintenance: "critical",
  Good: "ok", Fair: "low", Poor: "critical", Planning: "info", Active: "ok", Completed: "ok", Scheduled: "info", "In transit": "info", Delayed: "low", Cancelled: "critical",
  Open: "critical", Responding: "low", Contained: "info", Closed: "ok", Moderate: "low", High: "critical", Critical: "critical", Normal: "", Registered: "", Packed: "info", "In Transit": "info", Received: "ok", Delivered: "ok" };
const badge = (text, tone = TONE[text]) => `<span class="badge ${tone || ""}">${esc(text)}</span>`;
const S = { token: localStorage.getItem("pmc.token"), meta: null, mission: localStorage.getItem("pmc.mission"), online: true, tab: "assets", chat: [] };
const can = perm => S.meta && S.meta.permissions.includes(perm);
let main;

/* ---------- transport: API calls with an offline cache and write queue ---------- */
const queue = () => JSON.parse(localStorage.getItem("pmc.queue") || "[]");
const saveQueue = q => { localStorage.setItem("pmc.queue", JSON.stringify(q)); renderNet(); };
const send = (path, method, body) => {
  // Every call goes to one function URL and names the real route in __vpath (see polar/web.py).
  const [route, qs] = path.split("?");
  return fetch("/api/index?__vpath=" + encodeURIComponent("/api" + route) + (qs ? "&" + qs : ""), { method, headers: { "Content-Type": "application/json", ...(S.token ? { Authorization: "Bearer " + S.token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
};

async function api(path, method = "GET", body) {
  try {
    const res = await send(path, method, body);
    const data = await res.json();
    if (res.status === 401 && S.token) { signOut(); throw new Error("Session expired, please sign in again"); }
    if (!res.ok) throw new Error(data.error || res.statusText);
    if (method === "GET") { try { localStorage.setItem("pmc.c." + path, JSON.stringify(data)); } catch { /* storage full: ignore */ } }
    setOnline(true);
    return data;
  } catch (e) {
    if (!(e instanceof TypeError)) throw e;   // TypeError means the network is unreachable
    setOnline(false);
    if (method === "GET") {
      const cached = localStorage.getItem("pmc.c." + path);
      if (cached) return JSON.parse(cached);
      throw new Error("You are offline and this page has not been opened before");
    }
    saveQueue([...queue(), { path, method, body }]);
    toast("Offline: change saved and will sync when the connection returns");
    return { queued: true };
  }
}

async function sync() {
  const pending = queue();
  if (!pending.length) return;
  const left = [];
  for (const [i, job] of pending.entries()) {
    try {
      const res = await send(job.path, job.method, job.body);
      if (!res.ok) toast(`Sync skipped one change: ${(await res.json()).error}`, true);
    } catch { left.push(...pending.slice(i)); break; }
  }
  saveQueue(left);
  if (!left.length) { setOnline(true); toast("All offline changes synced"); route(); }
}
function setOnline(v) { if (S.online !== v) { S.online = v; renderNet(); } }
function renderNet() {
  const bar = $("#net"); if (!bar) return;
  const n = queue().length;
  bar.hidden = S.online && !n;
  bar.innerHTML = `<b>${S.online ? "Online" : "Offline mode"}</b> ${n ? `${n} change${n > 1 ? "s" : ""} waiting to sync` : "Showing the last saved data"}<button class="sm ghost" id="syncnow">Sync now</button>`;
  $("#syncnow").onclick = sync;
}
addEventListener("online", sync);
addEventListener("offline", () => setOnline(false));

/* ---------- small UI helpers ---------- */
function toast(msg, bad) { const t = $("#toast"); t.textContent = msg; t.className = "show" + (bad ? " bad" : ""); clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "", 3000); }
const table = (cols, rows, empty) => rows.length
    ? `<div class="tw"><table><thead><tr>${cols.map(c => `<th${c[0] === ">" ? ' class="n"' : ""}>${esc(c.replace(/^>/, ""))}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`
    : `<div class="tw"><p class="empty">${empty}</p></div>`;
const head = (title, sub, actions = "") => { $("#head").innerHTML = `<h1>${title}<small>${sub}</small></h1><div>${actions}</div>`; };
const uniq = (rows, key) => [...new Set(rows.map(r => r[key]).filter(Boolean))].sort();
const missionQuery = () => S.mission ? `?mission_id=${S.mission}` : "";
const labelOf = r => r.name || r.tag || r.code || r.title;

function dialog(html) {
  const d = document.createElement("dialog");
  d.innerHTML = `<div class="in">${html}</div>`;
  document.body.append(d); d.showModal();
  d.addEventListener("close", () => d.remove());
  d.querySelectorAll("[data-close]").forEach(b => b.onclick = () => d.close());
  return d;
}

/* Filterable, searchable list. `row` returns a <tr data-id> string; `onRow` receives the clicked record. */
function listView(root, data, { filters = [], columns, row, empty, onRow }) {
  root.innerHTML = `<div class="tools"><input id="q" placeholder="Search" style="min-width:220px">${filters.map(([k, label, opts]) =>
      `<select data-k="${k}"><option value="">${label}</option>${opts.map(o => `<option>${esc(o)}</option>`).join("")}</select>`).join("")}<span class="cnt"></span></div><div class="tbl"></div>`;
  const draw = () => {
    const q = $("#q", root).value.toLowerCase();
    const active = [...root.querySelectorAll("select[data-k]")].filter(s => s.value);
    const rows = data.filter(r => (!q || JSON.stringify(Object.values(r)).toLowerCase().includes(q)) && active.every(s => String(r[s.dataset.k]) === s.value));
    $(".cnt", root).textContent = rows.length + " records";
    const box = $(".tbl", root);
    box.innerHTML = table(columns, rows.map(row), empty);
    if (onRow) box.querySelectorAll("tr[data-id]").forEach(tr => tr.onclick = ev => { if (!ev.target.closest("button, select")) onRow(data.find(r => String(r.id) === tr.dataset.id)); });
  };
  root.querySelectorAll("#q, select[data-k]").forEach(e => e.oninput = draw);
  draw();
}

/* Create or edit any registered entity. The form is generated from the field definitions in /api/meta. */
async function editEntity(name, row = {}) {
  const spec = S.meta.entities[name], id = row.id;
  const refs = {};
  await Promise.all(spec.fields.filter(f => f.ref).map(async f => { refs[f.k] = await api("/" + f.ref); }));
  const control = f => {
    const v = row[f.k] ?? (f.k === "mission_id" && !id ? S.mission : "");
    if (f.t === "checkbox") return `<input type="checkbox" name="${f.k}" ${row[f.k] ? "checked" : ""}>`;
    if (f.t === "select") {
      const options = f.ref ? refs[f.k].map(o => [o.id, labelOf(o)]) : S.meta.enums[f.enum].map(o => [o, o]);
      return `<select name="${f.k}">${f.ref && !f.req ? '<option value=""></option>' : ""}${options.map(([a, b]) => `<option value="${esc(a)}" ${String(v) === String(a) ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>`;
    }
    return `<input name="${f.k}" type="${f.t === "number" ? "number" : f.t === "date" ? "date" : "text"}" step="any" value="${esc(v)}">`;
  };
  const singular = name.replace(/ies$/, "y").replace(/s$/, "");
  const d = dialog(`<form><h2>${id ? "Edit" : "Add"} ${singular}</h2><div class="fg">${spec.fields.map(f => `<label class="${f.w ? "w2" : ""}">${esc(f.l)}${f.req ? " *" : ""}${control(f)}</label>`).join("")}</div>
    <div class="fa">${id && can(spec.perm) ? '<button type="button" class="danger" id="del">Delete</button>' : ""}<span class="sp"></span><button type="button" class="ghost" data-close>Cancel</button>${can(spec.perm) ? "<button>Save</button>" : ""}</div></form>`);
  const finish = async action => { try { await action(); d.close(); toast("Saved"); route(); } catch (e) { toast(e.message, true); } };
  $("form", d).onsubmit = ev => {
    ev.preventDefault();
    const body = {};
    spec.fields.forEach(f => { const el = $(`[name="${f.k}"]`, d); body[f.k] = f.t === "checkbox" ? el.checked : el.value; });
    finish(() => id ? api(`/${name}/${id}`, "PATCH", body) : api("/" + name, "POST", body));
  };
  if ($("#del", d)) $("#del", d).onclick = () => confirm("Delete this record?") && finish(() => api(`/${name}/${id}`, "DELETE"));
}

/* ---------- sign-in and shell ---------- */
function showLogin(message = "") {
  $("#app").innerHTML = `<div class="login"><form id="lf"><div><h1>Polar Mission Control<small>Sign in to continue</small></h1></div>
    <label>Username<input name="username" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label>
    <p id="lerr">${esc(message)}</p><button>Sign in</button></form></div>`;
  $("#lf").onsubmit = async ev => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try {
      const res = await api("/login", "POST", { username: f.get("username"), password: f.get("password") });
      S.token = res.token; localStorage.setItem("pmc.token", res.token);
      await boot();
    } catch (e) { $("#lerr").textContent = e.message; }
  };
}
function signOut() {
  if (S.token) send("/logout", "POST", {}).catch(() => {});
  S.token = null; S.meta = null; localStorage.removeItem("pmc.token");
  showLogin();
}

const NAV = [["Operations", [["dashboard", "Mission control"], ["missions", "Expeditions"], ["cargo", "Cargo tracking"], ["people", "Personnel"], ["stock", "Assets and inventory"], ["emergency", "Emergency response"]]],
  ["Intelligence", [["copilot", "Expedition copilot", "copilot"], ["scenarios", "What-if planner", "scenario"]]], ["Records", [["audit", "Audit timeline", "audit"]]]];

async function boot() {
  try { S.meta = await api("/meta"); } catch (e) { return showLogin(e.message); }
  const missions = await api("/missions");
  if (!missions.some(m => String(m.id) === String(S.mission))) S.mission = missions[0] ? String(missions[0].id) : null;
  $("#app").innerHTML = `<div class="shell"><aside><div class="brand">Polar Mission Control<small>Expedition operations</small></div><nav>${NAV.map(([group, items]) =>
      `<span>${group}</span>${items.filter(i => !i[2] || can(i[2])).map(([id, label]) => `<a href="#${id}">${label}</a>`).join("")}`).join("")}</nav></aside>
    <div class="content"><div class="topbar"><label>Expedition <select id="mission">${missions.map(m => `<option value="${m.id}" ${String(m.id) === S.mission ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></label>
    <span class="sp"></span><span class="who">${esc(S.meta.user.name)} (${esc(S.meta.user.role.replace("_", " "))})</span><button class="ghost sm" id="out">Sign out</button></div>
    <div class="netbar" id="net" hidden></div><main><div class="head" id="head"></div><div id="main"></div></main></div></div>`;
  main = $("#main");
  $("#mission").onchange = e => { S.mission = e.target.value; localStorage.setItem("pmc.mission", S.mission); route(); };
  $("#out").onclick = signOut;
  renderNet(); sync(); route();
}

async function route() {
  if (!S.meta) return;
  const view = (location.hash || "#dashboard").slice(1);
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("on", a.hash === "#" + view));
  try { await (VIEWS[view] || VIEWS.dashboard)(); } catch (e) { main.innerHTML = `<div class="tw"><p class="empty" style="color:var(--bad)">${esc(e.message)}</p></div>`; }
}
addEventListener("hashchange", route);

/* ---------- mission control dashboard ---------- */
function polarMap(stations, south) {
  const cx = 150, cy = 150, R = 128, span = 40;
  const dist = s => south ? s.lat + 90 : 90 - s.lat;
  const xy = s => { const r = R * dist(s) / span, a = s.lon * Math.PI / 180; return [cx + r * Math.sin(a), cy - r * Math.cos(a)]; };
  const rings = [10, 20, 30, 40].map(d => `<circle class="ring${d === 40 ? "2" : ""}" cx="${cx}" cy="${cy}" r="${R * d / span}"/><text x="${cx + 3}" y="${cy - R * d / span + 10}">${(south ? -90 + d : 90 - d)}\u00b0${south ? "S" : "N"}</text>`).join("");
  const spokes = [0, 30, 60, 90, 120, 150].map(a => { const t = a * Math.PI / 180; return `<line class="ring" x1="${cx - R * Math.sin(t)}" y1="${cy + R * Math.cos(t)}" x2="${cx + R * Math.sin(t)}" y2="${cy - R * Math.cos(t)}"/>`; }).join("");
  const colour = { ok: "#2f9e6e", warning: "#e0a23a", critical: "#d64a3f" };
  const pts = stations.filter(s => s.lat !== null && (south ? s.lat < -50 : s.lat > 50)).map(s => { const [x, y] = xy(s);
    return `<g><title>${esc(s.name)}: ${s.people} people, ${s.open_incidents} open incidents, ${s.red_cargo} red cargo</title><circle cx="${x}" cy="${y}" r="7" fill="${colour[s.health]}" stroke="#fff" stroke-width="2"/><text class="lbl" x="${x + 10}" y="${y + 4}">${esc(s.name)}</text></g>`; }).join("");
  return `<svg viewBox="0 0 300 300" role="img" aria-label="${south ? "Antarctic" : "Arctic"} station map">${rings}${spokes}${pts}</svg>`;
}

async function dashboard() {
  const d = await api("/dashboard" + missionQuery());
  head(esc(d.mission.name), `${esc(d.mission.season || "")} / ${esc(d.mission.status)} / ${fmtDate(d.mission.start_date)} to ${fmtDate(d.mission.end_date)}`);
  const r = d.readiness, tone = v => v >= S.meta.thresholds.readiness_green ? "ok" : v >= S.meta.thresholds.readiness_amber ? "low" : "critical";
  const inFlight = d.cargo_by_status["In Transit"], red = d.cargo_by_risk.red;
  const people = Object.values(d.people_by_movement).reduce((a, b) => a + b, 0);
  const openInc = d.alerts.filter(a => a.area === "Emergency").length;
  main.innerHTML = `<div class="grid g4">${[["Mission readiness", r.overall + "%"], ["Cargo in transit", inFlight], ["Cargo at red risk", red], ["Personnel", people], ["Open incidents", openInc]].map(k => `<div class="kpi"><span>${k[0]}</span><b>${k[1]}</b></div>`).join("")}</div>
  <div class="grid g2"><div class="panel"><h2>Mission readiness</h2><div class="overall ${tone(r.overall)}" style="background:none">${r.overall}%</div>${r.dimensions.map(x =>
      `<div class="dim" title="${esc(x.detail)}"><span>${x.name}</span><div class="t"><div class="f ${TONE[x.level]}" style="width:${x.score}%"></div></div><span class="v">${x.score}</span></div>`).join("")}</div>
  <div class="panel"><h2>Station map</h2><div class="maps">${polarMap(d.stations, true)}${polarMap(d.stations, false)}</div><p class="sub">Marker colour shows open incidents and red cargo. Stations outside polar latitudes are listed in the Expeditions page.</p></div></div>
  <div class="panel" style="margin-bottom:14px"><h2>Cargo pipeline</h2><div class="flow">${Object.entries(d.cargo_by_status).map(([k, v]) => `<div><b>${v}</b><span>${k}</span></div>`).join("")}</div></div>
  <div class="grid g2"><div><h2>Deadline intelligence</h2>${table(["Transport", "Cut-off", ">Days", "Not packed", "Status"], d.deadlines.map(x =>
      `<tr><td>${esc(x.name)}</td><td>${fmtDate(x.cutoff)}</td><td class="n">${badge(x.days, x.days <= S.meta.thresholds.cutoff_red_days ? "critical" : x.days <= S.meta.thresholds.cutoff_amber_days ? "low" : "ok")}</td><td class="n">${x.unpacked}</td><td>${badge(x.status)}</td></tr>`), "No upcoming cut-offs.")}</div>
  <div class="panel"><h2>Alerts (${d.alerts.length})</h2>${d.alerts.slice(0, 12).map(a => `<div class="alert" data-route="${a.route}"><span class="a">${badge(a.area, a.level === "critical" ? "critical" : "low")}</span><span>${esc(a.text)}</span></div>`).join("") || '<p class="empty">No alerts.</p>'}</div></div>`;
  main.querySelectorAll("[data-route]").forEach(el => el.onclick = () => location.hash = el.dataset.route);
}

/* ---------- expeditions, transports and stations ---------- */
function timeline(transports) {
  const dated = transports.filter(t => t.depart && t.arrive);
  if (!dated.length) return '<p class="empty">No dated transports.</p>';
  const days = v => new Date(v + "T00:00").getTime() / 864e5;
  const lo = Math.min(...dated.map(t => days(t.cutoff || t.depart))) - 2, hi = Math.max(...dated.map(t => days(t.arrive))) + 2, today = Date.now() / 864e5;
  const pct = v => (days(v) - lo) / (hi - lo) * 100;
  return `<div class="tlw">${today > lo && today < hi ? `<div class="today" style="left:${(today - lo) / (hi - lo) * 100}%" title="Today"></div>` : ""}${dated.map(t =>
      `<div class="tl"><span class="nm" style="left:${pct(t.depart)}%">${esc(t.name)} ${badge(t.status)}</span><div class="lane" style="left:${pct(t.depart)}%;width:${pct(t.arrive) - pct(t.depart)}%" title="${fmtDate(t.depart)} to ${fmtDate(t.arrive)}"></div>${t.cutoff ? `<div class="cut" style="left:${pct(t.cutoff)}%" title="Cargo cut-off ${fmtDate(t.cutoff)}"></div>` : ""}</div>`).join("")}</div>
    <p class="sub">Bars show departure to arrival, diamonds mark the cargo cut-off, the red line is today.</p>`;
}

async function missions() {
  const [ms, ts, ss] = await Promise.all([api("/missions"), api("/transports" + missionQuery()), api("/stations")]);
  head("Expeditions", "Programmes, transport legs and stations", can("mission") ? '<button id="addm">Add expedition</button> <button class="ghost" id="adds">Add station</button>' : "");
  if (can("mission")) { $("#addm").onclick = () => editEntity("missions"); $("#adds").onclick = () => editEntity("stations"); }
  main.innerHTML = `<h2>Expeditions</h2><div id="m"></div><h2 style="margin-top:22px">Transport timeline</h2><div class="panel">${timeline(ts)}</div>
    <div class="head" style="margin-top:22px"><h2>Transport legs</h2>${can("logistics") ? '<button class="sm" id="addt">Add transport</button>' : ""}</div><div id="t"></div><h2 style="margin-top:22px">Stations</h2><div id="s"></div>`;
  if (can("logistics")) $("#addt").onclick = () => editEntity("transports");
  $("#m").innerHTML = table(["Code", "Expedition", "Season", "Status", "Dates"], ms.map(m => `<tr class="click" data-id="${m.id}"><td>${esc(m.code)}</td><td>${esc(m.name)}<span class="sub">${esc(m.description)}</span></td><td>${esc(m.season)}</td><td>${badge(m.status)}</td><td>${fmtDate(m.start_date)} to ${fmtDate(m.end_date)}</td></tr>`), "No expeditions.");
  $("#m").querySelectorAll("tr[data-id]").forEach(tr => tr.onclick = () => editEntity("missions", ms.find(m => String(m.id) === tr.dataset.id)));
  listView($("#t"), ts, { filters: [["status", "All statuses", S.meta.enums.transport_status]], columns: ["Transport", "Route", "Departure", "Cargo cut-off", ">Load (t)", ">Cargo lines", "Status"], empty: "No transports.", onRow: r => editEntity("transports", r),
    row: t => `<tr class="click" data-id="${t.id}"><td>${esc(t.name)}<span class="sub">${esc(t.mode)}</span></td><td>${esc(t.origin)} to ${esc(t.station)}</td><td>${fmtDate(t.depart)}</td><td>${fmtDate(t.cutoff)}</td><td class="n">${num(t.load_t)} / ${num(t.cargo_capacity_t)} ${t.over_capacity ? badge("Over", "critical") : ""}</td><td class="n">${t.cargo_count}</td><td>${badge(t.status)}</td></tr>` });
  listView($("#s"), ss, { filters: [["region", "All regions", uniq(ss, "region")]], columns: ["Station", "Region", "Coordinates", ">Crew", "Status"], empty: "No stations.", onRow: r => editEntity("stations", r),
    row: s => `<tr class="click" data-id="${s.id}"><td>${esc(s.name)}<span class="sub">${esc(s.type)}</span></td><td>${esc(s.region)}</td><td>${s.lat ?? "-"}, ${s.lon ?? "-"}</td><td class="n">${num(s.crew)} / ${num(s.crew_capacity)}</td><td>${badge(s.status, s.status === "Operational" ? "ok" : "low")}</td></tr>` });
}

/* ---------- cargo tracking ---------- */
async function cargoDetail(row) {
  const trail = await api(`/cargo/${row.id}/custody`);
  const d = dialog(`<h2>${esc(row.code)} ${badge(row.risk, TONE[row.risk])} ${badge(row.status)}</h2><p>${esc(row.description)}</p>
    <div style="display:flex;gap:20px;flex-wrap:wrap"><div><img class="qr" src="/api/index?__vpath=/api/qr/${esc(row.code)}.svg" alt="QR code for ${esc(row.code)}" onerror="this.outerHTML='<div class=&quot;qrfallback&quot;>QR unavailable. Install segno to enable labels.</div>'"></div>
    <div style="flex:1;min-width:240px"><table><tbody>${[["Category", row.category], ["Destination", row.station], ["Transport", row.transport], ["Cut-off", `${fmtDate(row.cutoff)} (${row.days_to_cutoff ?? "-"} days)`], ["Weight", `${num(row.weight_kg)} kg / ${num(row.volume_m3)} m3`],
    ["Priority", row.priority], ["Owner", row.owner], ["Paperwork", row.docs_complete ? "Complete" : "Incomplete"]].map(([k, v]) => `<tr><td>${k}</td><td>${esc(v ?? "-")}</td></tr>`).join("")}</tbody></table></div></div>
    <h3>Risk assessment</h3>${row.risk_reasons.length ? `<ul>${row.risk_reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : "<p>No issues detected.</p>"}
    <h3>Chain of custody</h3><ul class="steps">${trail.map(e => `<li><b>${esc(e.status)}</b> at ${esc(e.location || "-")}<span class="sub">${fmtTime(e.ts)} / ${esc(e.handler)}${e.note ? " / " + esc(e.note) : ""}</span></li>`).join("")}</ul>
    <div class="fa"><span class="sp"></span>${can("logistics") ? '<button class="ghost" id="edit">Edit</button>' : ""}${can("logistics") && row.next_status ? `<button id="adv">Mark as ${esc(row.next_status)}</button>` : ""}<button class="ghost" data-close>Close</button></div>`);
  if ($("#edit", d)) $("#edit", d).onclick = () => { d.close(); editEntity("cargo", row); };
  if ($("#adv", d)) $("#adv", d).onclick = () => {
    d.close();
    const f = dialog(`<form><h2>Record handover: ${esc(row.next_status)}</h2><div class="fg"><label>Location<input name="location"></label><label>Handler<input name="handler" placeholder="${esc(S.meta.user.name)}"></label><label class="w2">Note<input name="note"></label></div>
      <div class="fa"><span class="sp"></span><button type="button" class="ghost" data-close>Cancel</button><button>Confirm</button></div></form>`);
    $("form", f).onsubmit = async ev => { ev.preventDefault(); const b = Object.fromEntries(new FormData(ev.target)); try { await api(`/cargo/${row.id}/advance`, "POST", b); f.close(); toast("Custody updated"); route(); } catch (e) { toast(e.message, true); } };
  };
}

async function cargo() {
  const rows = await api("/cargo" + missionQuery());
  head("Cargo tracking", "Consignments, custody and deadline risk", can("logistics") ? '<button id="add">Register cargo</button>' : "");
  if (can("logistics")) $("#add").onclick = () => editEntity("cargo");
  main.innerHTML = `<div class="tools"><input id="scan" placeholder="Scan or enter cargo code, e.g. CGO-2026-0001"><button class="ghost" id="go">Look up</button></div><div id="list"></div>`;
  $("#go").onclick = async () => { try { const r = await api("/cargo/track/" + encodeURIComponent($("#scan").value.trim())); cargoDetail(r.cargo); } catch (e) { toast(e.message, true); } };
  $("#scan").onkeydown = e => e.key === "Enter" && $("#go").click();
  listView($("#list"), rows, { filters: [["status", "All statuses", S.meta.cargo_flow], ["risk", "Any risk", ["green", "amber", "red"]], ["priority", "Any priority", S.meta.enums.priority], ["station", "All destinations", uniq(rows, "station")]],
    columns: ["Code", "Consignment", "Destination", "Transport", ">Cut-off (days)", "Status", "Risk", "Papers"], empty: "No cargo registered.", onRow: cargoDetail,
    row: c => `<tr class="click" data-id="${c.id}"><td>${esc(c.code)}</td><td>${esc(c.description)}<span class="sub">${esc(c.category)} / ${num(c.weight_kg)} kg${c.hazard ? " / hazardous" : ""}</span></td><td>${esc(c.station)}</td><td>${esc(c.transport || "-")}</td>
      <td class="n">${c.days_to_cutoff ?? "-"}</td><td>${badge(c.status)}</td><td><span title="${esc(c.risk_reasons.join("; "))}">${badge(c.risk, TONE[c.risk])}</span></td><td>${c.docs_complete ? badge("Complete", "ok") : badge("Missing", "critical")}</td></tr>` });
}

/* ---------- personnel movement board ---------- */
async function people() {
  const rows = await api("/personnel" + missionQuery());
  head("Personnel movement", "Deployment status and clearances", can("people") ? '<button id="add">Add person</button>' : "");
  if (can("people")) $("#add").onclick = () => editEntity("personnel");
  const stations = Object.fromEntries((await api("/stations")).map(s => [s.id, s.name]));
  const chip = (ok, l) => `<span class="chip ${ok ? "ok" : "critical"}" title="${l} clearance ${ok ? "granted" : "missing"}">${l[0]}</span>`;
  main.innerHTML = `<div class="board">${S.meta.enums.movement.map(m => { const col = rows.filter(p => p.movement_status === m);
    return `<div class="col"><h2>${m}<span>${col.length}</span></h2>${col.map(p => `<div class="card"><b data-id="${p.id}">${esc(p.name)}</b><span class="sub">${esc(p.role)} / ${esc(stations[p.station_id] || "-")}</span>${chip(p.medical_cleared, "Medical")}${chip(p.training_cleared, "Training")}${chip(p.permit_cleared, "Permit")}
      ${can("people") ? `<select data-move="${p.id}">${S.meta.enums.movement.map(o => `<option ${o === m ? "selected" : ""}>${o}</option>`).join("")}</select>` : ""}</div>`).join("") || '<p class="sub">Nobody</p>'}</div>`; }).join("")}</div>`;
  main.querySelectorAll("b[data-id]").forEach(b => b.onclick = () => editEntity("personnel", rows.find(p => String(p.id) === b.dataset.id)));
  main.querySelectorAll("select[data-move]").forEach(s => s.onchange = async () => { try { await api(`/personnel/${s.dataset.move}`, "PATCH", { movement_status: s.value }); toast("Movement updated"); route(); } catch (e) { toast(e.message, true); } });
}

/* ---------- assets and inventory ---------- */
async function stock() {
  const [assets, items] = await Promise.all([api("/assets"), api("/items")]);
  const isAssets = S.tab === "assets";
  head("Assets and inventory", "Equipment condition and supply cover by station", can("logistics") ? `<button id="add">Add ${isAssets ? "asset" : "item"}</button>` : "");
  if (can("logistics")) $("#add").onclick = () => editEntity(isAssets ? "assets" : "items");
  main.innerHTML = `<div class="tools"><button class="${isAssets ? "" : "ghost"}" data-tab="assets">Assets (${assets.length})</button><button class="${isAssets ? "ghost" : ""}" data-tab="items">Inventory (${items.length})</button></div><div id="list"></div>`;
  main.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { S.tab = b.dataset.tab; route(); });
  if (isAssets) listView($("#list"), assets, { filters: [["station", "All stations", uniq(assets, "station")], ["category", "All categories", uniq(assets, "category")], ["status", "All statuses", S.meta.enums.asset_status], ["condition", "Any condition", S.meta.enums.condition]],
    columns: ["Tag", "Asset", "Station", "Status", "Condition", ">Hours to service", ">Total hours"], empty: "No assets.", onRow: r => editEntity("assets", r),
    row: a => `<tr class="click" data-id="${a.id}"><td>${esc(a.tag)}</td><td>${esc(a.name)}<span class="sub">${esc(a.model)} / ${esc(a.serial)}</span></td><td>${esc(a.station)}</td><td>${badge(a.status)}</td><td>${badge(a.condition)}</td><td class="n" style="${a.service_due ? "color:var(--bad);font-weight:600" : ""}">${num(a.service_hours)}</td><td class="n">${num(a.total_hours)}</td></tr>` });
  else listView($("#list"), items, { filters: [["station", "All stations", uniq(items, "station")], ["category", "All categories", uniq(items, "category")], ["level", "Any cover level", ["critical", "low", "ok"]], ["criticality", "Any criticality", S.meta.enums.criticality]],
    columns: ["Item", "Station", ">Stock", ">Use per day", ">Cover (days)", "Level", "Expiry", ">Value"], empty: "No items.", onRow: r => editEntity("items", r),
    row: i => `<tr class="click" data-id="${i.id}"><td>${esc(i.name)}<span class="sub">${esc(i.supplier)} / ${esc(i.location)}</span></td><td>${esc(i.station)}</td><td class="n">${num(i.stock)} ${esc(i.unit)}</td><td class="n">${num(i.use_per_day)}</td><td class="n">${num(i.cover_days)}</td><td>${badge(i.level, TONE[i.level])}</td>
      <td>${fmtDate(i.expiry)}${i.days_to_expiry !== null && i.days_to_expiry < S.meta.thresholds.expiry_warn_days ? `<span class="sub" style="color:var(--bad)">${i.days_to_expiry < 0 ? "Expired" : i.days_to_expiry + " days left"}</span>` : ""}</td><td class="n">${inr(i.value)}</td></tr>` });
}

/* ---------- emergency response ---------- */
async function reportIncident() {
  const stations = await api("/stations");
  const d = dialog(`<form><h2>Report incident</h2><div class="fg"><label>Station<select name="station_id">${stations.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></label>
    <label>Type<select name="type">${S.meta.enums.incident_type.map(o => `<option>${o}</option>`).join("")}</select></label><label>Severity<select name="severity">${S.meta.enums.severity.map(o => `<option>${o}</option>`).join("")}</select></label>
    <label>Reported by<input name="reporter" placeholder="${esc(S.meta.user.name)}"></label><label class="w2">Title<input name="title" required></label><label class="w2">Description<input name="description"></label></div>
    <h3>Affected personnel at this station</h3><div id="ppl"></div><div class="fa"><span class="sp"></span><button type="button" class="ghost" data-close>Cancel</button><button>Report</button></div></form>`);
  const loadPeople = async () => { const list = await api("/personnel?station_id=" + $("[name=station_id]", d).value); $("#ppl", d).innerHTML = list.map(p => `<label style="display:block"><input type="checkbox" value="${p.id}"> ${esc(p.name)} <span class="sub" style="display:inline">${esc(p.role)}</span></label>`).join("") || '<p class="sub">No registered personnel.</p>'; };
  $("[name=station_id]", d).onchange = loadPeople; loadPeople();
  $("form", d).onsubmit = async ev => {
    ev.preventDefault();
    const body = Object.fromEntries(new FormData(ev.target)); body.mission_id = S.mission; body.personnel_ids = [...d.querySelectorAll("#ppl input:checked")].map(i => i.value);
    try { await api("/incidents", "POST", body); d.close(); toast("Incident reported"); route(); } catch (e) { toast(e.message, true); }
  };
}

async function incidentDetail(id) {
  const i = await api("/incidents/" + id), editable = can("incident");
  const d = dialog(`<h2>${esc(i.title)}</h2><p>${badge(i.severity)} ${badge(i.status)} <span class="sub" style="display:inline">${esc(i.type)} at ${esc(i.station)}, reported ${fmtTime(i.reported_at)} by ${esc(i.reporter)}</span></p><p>${esc(i.description)}</p>
    <h3>Affected personnel (${i.people.length})</h3><p>${i.people.map(p => `${esc(p.name)} <span class="sub" style="display:inline">${esc(p.role)}, ${esc(p.contact || "no contact")}</span>`).join("<br>") || "None recorded"}</p>
    <h3>Response actions</h3>${table(["Action", "Assignee", "Status"], i.actions.map(a => `<tr><td>${esc(a.action)}</td><td>${esc(a.assignee || "-")}</td><td>${editable ? `<select data-act="${a.id}">${S.meta.enums.action_status.map(s => `<option ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}</select>` : esc(a.status)}</td></tr>`), "No actions yet.")}
    ${editable ? `<form id="af" class="tools" style="margin-top:10px"><input name="action" placeholder="New response action" style="flex:2" required><input name="assignee" placeholder="Assignee" style="flex:1"><button class="sm">Add action</button></form>
    <h3>Move incident to</h3><div class="tools">${S.meta.enums.incident_status.filter(s => s !== i.status).map(s => `<button class="ghost sm" data-status="${s}">${s}</button>`).join("")}</div>` : ""}
    <div class="fa"><span class="sp"></span><button class="ghost" data-close>Close</button></div>`);
  const run = async (fn, msg) => { try { await fn(); toast(msg); d.close(); await route(); incidentDetail(id); } catch (e) { toast(e.message, true); } };
  d.querySelectorAll("[data-act]").forEach(s => s.onchange = () => run(() => api(`/incidents/${id}/actions/${s.dataset.act}`, "PATCH", { status: s.value }), "Action updated"));
  d.querySelectorAll("[data-status]").forEach(b => b.onclick = () => run(() => api(`/incidents/${id}/status`, "POST", { status: b.dataset.status }), "Incident updated"));
  if ($("#af", d)) $("#af", d).onsubmit = ev => { ev.preventDefault(); run(() => api(`/incidents/${id}/actions`, "POST", Object.fromEntries(new FormData(ev.target))), "Action added"); };
}

async function emergency() {
  const rows = await api("/incidents" + missionQuery());
  head("Emergency response", "Incidents, affected personnel and response actions", can("incident") ? '<button id="add">Report incident</button>' : "");
  if (can("incident")) $("#add").onclick = reportIncident;
  main.innerHTML = '<div id="list"></div>';
  listView($("#list"), rows, { filters: [["status", "All statuses", S.meta.enums.incident_status], ["severity", "Any severity", S.meta.enums.severity], ["station", "All stations", uniq(rows, "station")]],
    columns: ["Incident", "Station", "Severity", "Status", ">People", ">Open actions", "Reported"], empty: "No incidents recorded.", onRow: r => incidentDetail(r.id),
    row: i => `<tr class="click" data-id="${i.id}"><td>${esc(i.title)}<span class="sub">${esc(i.type)}</span></td><td>${esc(i.station)}</td><td>${badge(i.severity)}</td><td>${badge(i.status)}</td><td class="n">${i.people_count}</td><td class="n">${i.pending_actions}</td><td>${fmtTime(i.reported_at)}</td></tr>` });
}

/* ---------- copilot, what-if planner, audit ---------- */
const resultTables = r => (r.tables || []).map(t => `<h3>${esc(t.title)}</h3>${table(t.columns, t.rows.map(cells => `<tr>${cells.map(c => `<td>${esc(c ?? "-")}</td>`).join("")}</tr>`), "Nothing to show.")}`).join("");

async function copilot() {
  const tips = await api("/copilot/suggestions");
  head("Expedition copilot", "Ask operational questions in plain language");
  const draw = () => { $("#log").innerHTML = S.chat.map(m => m.me ? `<div class="msg me">${esc(m.text)}</div>` : `<div class="msg bot"><b>${esc(m.answer)}</b>${resultTables(m)}</div>`).join(""); };
  main.innerHTML = `<div class="sugg">${tips.map(t => `<button class="ghost sm">${esc(t)}</button>`).join("")}</div><div class="chat" id="log"></div><form id="ask" class="tools" style="margin-top:14px"><input name="q" placeholder="Ask about cargo, assets, stock, people, incidents, deadlines or readiness" style="flex:1" required><button>Ask</button></form>`;
  const ask = async text => { S.chat.push({ me: true, text }); draw(); try { S.chat.push(await api("/copilot/ask", "POST", { question: text, mission_id: S.mission })); } catch (e) { S.chat.push({ answer: e.message, tables: [] }); } draw(); };
  main.querySelectorAll(".sugg button").forEach(b => b.onclick = () => ask(b.textContent));
  $("#ask").onsubmit = ev => { ev.preventDefault(); const q = $("[name=q]", ev.target); ask(q.value); q.value = ""; };
  draw();
}

async function scenarios() {
  const types = await api("/scenarios/types");
  head("What-if planner", "Test the effect of delays, cancellations, cargo loss or evacuation. Nothing is changed.");
  main.innerHTML = `<div class="panel"><form id="sf" class="tools"><label>Scenario<select name="type">${types.map(t => `<option value="${t.id}">${esc(t.label)}</option>`).join("")}</select></label><label>Applies to<select name="target_id"></select></label><span id="params"></span><button>Run scenario</button></form></div><div id="out" style="margin-top:14px"></div>`;
  const sel = () => types.find(t => t.id === $("[name=type]").value);
  const fill = async () => {
    const t = sel(), rows = await api("/" + t.target + (t.target === "stations" ? "" : missionQuery()));
    $("[name=target_id]").innerHTML = rows.map(r => `<option value="${r.id}">${esc(r.code && !r.name ? r.code : r.name || r.code)}${r.description ? " " + esc(r.description.slice(0, 40)) : ""}</option>`).join("");
    $("#params").innerHTML = t.params.map(p => `<label>${esc(p.l)}<input name="${p.k}" type="number" min="1" value="${p.default}" style="width:90px"></label>`).join("");
  };
  $("[name=type]").onchange = fill; await fill();
  $("#sf").onsubmit = async ev => {
    ev.preventDefault();
    try { const r = await api("/scenarios/run", "POST", Object.fromEntries(new FormData(ev.target))); $("#out").innerHTML = `<div class="panel"><h2>${esc(r.title)}</h2><ul>${r.summary.map(s => `<li>${esc(s)}</li>`).join("")}</ul>${resultTables(r)}</div>`; } catch (e) { toast(e.message, true); }
  };
}

async function audit() {
  const rows = await api("/audit?limit=200");
  head("Audit timeline", "Every change, who made it and when");
  main.innerHTML = '<div id="list"></div>';
  listView($("#list"), rows, { filters: [["entity", "All records", uniq(rows, "entity")], ["actor", "All users", uniq(rows, "actor")]], columns: ["Time", "User", "Action", "Record", "Detail"], empty: "No activity yet.",
    row: a => `<tr><td>${fmtTime(a.ts)}</td><td>${esc(a.actor)}</td><td>${esc(a.action)}</td><td>${esc(a.entity || "-")}${a.entity_id ? " #" + a.entity_id : ""}</td><td>${esc(a.detail)}</td></tr>` });
}

const VIEWS = { dashboard, missions, cargo, people, stock, emergency, copilot, scenarios, audit };

/* ---------- start ---------- */
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
if (S.token) boot(); else showLogin();