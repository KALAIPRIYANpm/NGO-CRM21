/* NGO Suite front-end core: helpers, auth, router, registers, admin. No external libraries. */
"use strict";
let META = null, USER = null, BRAND = { product: "NGO Suite", color: "#0f5e63", note: "Donors, projects, people, grants and accounts in one place.", logo: "" };
const $ = (s, e = document) => e.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) { if (c == null || c === false) continue; e.append(c.nodeType ? c : document.createTextNode(String(c))); }
  return e;
}
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const IN2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const money = v => v == null || v === "" ? "–" : (v < 0 ? "-₹" : "₹") + IN.format(Math.abs(Math.round(v)));
const num = v => v == null || v === "" ? "–" : IN2.format(v);
const pct = v => v == null || v === "" ? "–" : Math.round(v * 100) + "%";
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fd = s => { if (!s) return "–"; const [y, m, d] = String(s).slice(0, 10).split("-"); return `${+d} ${MON[+m - 1]} ${y}`; };
const fm = ym => { const [y, m] = ym.split("-"); return MON[+m - 1] + " " + y.slice(2); };
const todayISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const asofISO = () => (META && META.settings.asof_override) || todayISO();
function prevMonth() { const d = new Date(asofISO()); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 7); }
const can = t => USER && META.tables[t].write.includes(USER.role);

function toast(msg, err) { const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : ""); clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "", err ? 5000 : 2500); }
async function api(method, path, body) {
  let r;
  try { r = await fetch("/api" + path, { method, headers: body !== undefined ? { "Content-Type": "application/json" } : {}, body: body !== undefined ? JSON.stringify(body) : undefined, credentials: "same-origin" }); }
  catch (e) { const er = new Error("No network connection"); er.status = 0; throw er; }
  let data = null; const ct = r.headers.get("Content-Type") || "";
  if (ct.includes("json")) data = await r.json();
  if (!r.ok) { if (r.status === 401 && !path.startsWith("/login")) { USER = null; showLogin(); } const er = new Error((data && data.error) || "Request failed"); er.status = r.status; throw er; }
  return data;
}
const get = p => api("GET", p), post = (p, b) => api("POST", p, b), put = (p, b) => api("PUT", p, b), del = p => api("DELETE", p);
const must = async fn => { try { return await fn(); } catch (e) { toast(e.message, true); return undefined; } };

/* ---------------- tooltip ---------------- */
function tip(el, text) {
  let t = $(".tip") || document.body.appendChild(h("div", { class: "tip" }));
  el.addEventListener("mousemove", e => { t.textContent = text; t.style.display = "block"; t.style.left = e.clientX + 12 + "px"; t.style.top = e.clientY + 12 + "px"; });
  el.addEventListener("mouseleave", () => t.style.display = "none");
}

/* ---------------- modal ---------------- */
function modal(title, body, opts = {}) {
  const root = $("#modal-root");
  const close = () => { bg.remove(); document.removeEventListener("keydown", esc_); };
  const esc_ = e => { if (e.key === "Escape") close(); };
  const bg = h("div", { class: "modal-bg", onmousedown: e => { if (e.target === bg) close(); } }, h("div", { class: "modal" + (opts.wide ? " wide" : ""), role: "dialog", "aria-label": title }, h("h2", {}, title), body));
  document.addEventListener("keydown", esc_); root.append(bg);
  const f = bg.querySelector("input,select,textarea"); if (f) f.focus();
  return close;
}
function confirmBox(msg, onYes, label = "Delete") {
  const close = modal("Please confirm", h("div", {}, h("p", {}, msg), h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"), h("button", { class: "btn pri", onclick: () => { close(); onYes(); } }, label))));
}

/* ---------------- branding (white label) ---------------- */
function shade(hex, f) { const n = [1, 3, 5].map(i => Math.max(0, Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * f)))); return "#" + n.map(x => x.toString(16).padStart(2, "0")).join(""); }
function applyBrand(b) {
  BRAND = { ...BRAND, ...b };
  const r = document.documentElement.style, own = window.accentChoice ? window.accentChoice() : "", c = own || (/^#[0-9a-fA-F]{6}$/.test(BRAND.color) ? BRAND.color : "#0f5e63");
  r.setProperty("--brand", c); r.setProperty("--brand2", shade(c, .78));
  const mix = [1, 3, 5].map(i => Math.round(parseInt(c.slice(i, i + 2), 16) * .12 + 255 * .88).toString(16).padStart(2, "0")).join("");
  r.setProperty("--brand-soft", "#" + mix);
  document.title = BRAND.product;
}
async function loadBrand() { try { applyBrand(await get("/public/brand")); } catch (e) { /* keep defaults */ } }
const logoImg = (cls, size) => BRAND.logo ? h("img", { src: BRAND.logo, alt: "", class: cls, style: `max-height:${size}px;max-width:100%;display:block` }) : null;

/* ---------------- login ---------------- */
function showLogin() {
  const app = $("#app"); app.replaceChildren();
  const u = h("input", { id: "u", autocomplete: "username", autofocus: true }), p = h("input", { id: "p", type: "password", autocomplete: "current-password" });
  const go = async () => { try { const r = await post("/login", { username: u.value, password: p.value }); if (r && r.need_2fa) return askCode(r.pre); await boot(); } catch (e) { toast(e.message, true); } };
  p.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  app.append(h("div", { class: "card login" }, logoImg("", 64), h("h1", {}, BRAND.product), h("div", { class: "sub" }, BRAND.note),
    h("div", { class: "f" }, h("label", {}, "Username"), u), h("div", { class: "f" }, h("label", {}, "Password"), p), h("button", { class: "btn pri", onclick: go }, "Sign in"), h("div", { class: "hint", style: "margin-top:12px;text-align:center" }, "Version: " + (BRAND.version || "old"))));
}
function forcePassword() {
  const o = h("input", { type: "password" }), n = h("input", { type: "password" });
  modal("Choose a new password", h("div", {}, h("p", {}, "For safety, set your own password (at least 8 characters)."), h("label", {}, "Current password"), o, h("label", { style: "margin-top:8px" }, "New password"), n,
    h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: async () => { if (await must(() => post("/password", { old: o.value, new: n.value }))) location.reload(); } }, "Save password"))));
}

/* ---------------- shell + router ---------------- */
const NAV = [
  ["Overview", [["Dashboard", "#/dashboard"], ["Weekly summary", "#/r/weekly"], ["Automations", "#/r/automation"], ["Field app (phone)", "#/r/field"]]],
  ["Communicate", [["Follow-ups", "#/r/followups"], ["Inbox", "#/r/inbox"], ["Broadcast", "#/r/messages"], ["Contacts", "#/t/contacts"], ["Social posts", "#/t/social_posts"], ["Post ideas", "#/r/social"], ["Contact log", "#/t/interactions"], ["Message templates", "#/t/templates"], ["Birthdays", "#/r/birthdays"]]],
  ["Fundraising", [["Donors", "#/t/donors"], ["Donations", "#/t/donations"], ["Pledges", "#/t/pledges"], ["Giving promises", "#/r/promises"], ["Donors slipping away", "#/r/lapse"], ["Donor insights", "#/r/donors"], ["Find duplicates", "#/r/dups"], ["Company partners", "#/r/partners"], ["Office events", "#/t/partner_events"], ["Event people", "#/t/event_people"], ["Key relationships", "#/r/relations"], ["Company funding pipeline", "#/t/csr_pipeline"], ["Legacy pipeline", "#/t/legacies"], ["Sponsor outcomes", "#/t/outcomes"]]],
  ["Programmes", [["Projects", "#/t/projects"], ["Project board", "#/r/projects"], ["Beneficiaries", "#/t/beneficiaries"], ["Journey", "#/r/journey"], ["Journey steps", "#/t/journey"], ["Activity log", "#/t/activities"], ["Photos & videos", "#/r/gallery"], ["Results", "#/t/results"], ["Project money", "#/t/project_spend"]]],
  ["People & pay", [["Team", "#/t/team"], ["Daily attendance", "#/t/attendance"], ["Volunteer log", "#/t/volunteer_log"], ["Payroll", "#/r/payroll"]]],
  ["Grants", [["Grants", "#/t/grants"], ["Grant dashboard", "#/r/grants"], ["Expected payments", "#/t/tranches"], ["Instalments", "#/t/instalments"], ["Grant spend", "#/t/grant_spend"]]],
  ["Accounts", [["Funds", "#/t/funds"], ["Cash book", "#/t/cash_book"], ["Expense claims", "#/r/claims"], ["Bank import", "#/r/bank"], ["Fund dashboard", "#/r/funds"], ["Trustee report", "#/r/trustee"], ["Compliance calendar", "#/t/compliance"], ["Audit and 80G pack", "#/r/pack"]]],
  ["Planning", [["Cash forecast", "#/r/forecast"], ["Board pack", "#/r/board"], ["Yearly plan", "#/r/yearplan"], ["Festival calendar", "#/t/plan_calendar"], ["Board decisions", "#/t/decisions"], ["Planning tools", "#/r/budget"], ["Budget lines", "#/t/budget_lines"], ["Appeals", "#/t/appeals"], ["Cash flow plan", "#/t/cashflow_plan"]]],
  ["Reports", [["Donor impact report", "#/r/impact"], ["Funder report (CSR)", "#/r/csr"], ["CSR proposal", "#/r/proposal"], ["Impact cards (share link)", "#/r/cards"], ["All projects", "#/r/allprojects"]]],
  ["Governance", [["Yearly compliance check", "#/r/yearcheck"], ["Risk map", "#/r/riskmap"], ["Risk register", "#/t/risks"], ["Incidents", "#/t/incidents"], ["Policy register", "#/t/policies"], ["Trustees and members", "#/t/trustees"], ["Meetings and minutes", "#/t/meetings"]]],
  ["Documents", [["Official documents", "#/t/official_docs"], ["Print a format", "#/r/formats"], ["Records", "#/t/records"], ["Record lines", "#/t/record_lines"]]],
  ["Help", [["Help and page guide", "#/r/help"]]],
  ["Admin", [["Branding & setup", "#/a/branding"], ["Settings", "#/a/settings"], ["Dropdown lists", "#/a/lists"], ["Users", "#/a/users"], ["Backup & restore", "#/a/audit"], ["Audit trail", "#/a/auditlog"]]],
];
const NEWNAV = new Set(["#/r/proposal", "#/t/official_docs", "#/r/yearplan", "#/t/plan_calendar", "#/t/csr_pipeline", "#/t/social_posts", "#/r/social", "#/t/policies", "#/t/trustees", "#/t/meetings", "#/r/partners", "#/t/partner_events", "#/r/relations", "#/t/tranches", "#/r/forecast", "#/r/board", "#/t/decisions", "#/r/inbox", "#/r/promises", "#/r/lapse", "#/r/journey", "#/r/dups", "#/r/csr", "#/r/weekly", "#/a/auditlog", "#/t/event_people", "#/t/legacies", "#/t/outcomes", "#/r/yearcheck", "#/r/riskmap", "#/t/risks", "#/t/incidents", "#/r/help"]);   // pages added in the last two releases
const navState = { get() { try { return JSON.parse(localStorage.getItem("ngo_nav") || "{}"); } catch (e) { return {}; } }, set(o) { try { localStorage.setItem("ngo_nav", JSON.stringify(o)); } catch (e) { /* storage blocked */ } } };
function buildNav() {
  const st = navState.get();
  const find = h("input", { type: "search", placeholder: "Find a page…  ( / )", "aria-label": "Find a page", class: "navfind" });
  const nav = h("nav", { class: "side", "aria-label": "Main" }, logoImg("", 40) ? h("div", { style: "padding:6px 10px;background:#fff;border-radius:8px;margin:0 4px 6px" }, logoImg("", 40)) : null, h("div", { class: "brand" }, BRAND.product), h("div", { class: "org" }, META.settings.org_name), find);
  nav.dataset.v = BRAND.version || "";
  const boxes = [];
  for (const [g, items] of NAV) {
    if (g === "Admin" && USER.role !== "admin") continue;
    const links = [];
    for (const [l, href] of items) {
      const tm = href.match(/^#\/t\/(\w+)/);
      if (tm && META.tables[tm[1]] && !META.tables[tm[1]].read.includes(USER.role)) continue;
      if (href === "#/r/claims" && USER.role === "viewer") continue;
      if (href === "#/r/social" && USER.role === "viewer") continue;
      if (href === "#/r/yearplan" && !["admin", "accountant"].includes(USER.role)) continue;
      if (href === "#/r/inbox" && !["admin", "accountant"].includes(USER.role)) continue;
      if (href === "#/r/pack" && !["admin", "accountant"].includes(USER.role)) continue;
      if (href === "#/r/cards" && USER.role === "viewer") continue;
      if (href === "#/r/field" && !["admin", "programme"].includes(USER.role)) continue;
      if (href === "#/r/bank" && !["admin", "accountant"].includes(USER.role)) continue;
      if (["#/r/promises", "#/r/lapse", "#/r/weekly"].includes(href) && !["admin", "accountant"].includes(USER.role)) continue;
      if (href === "#/r/dups" && USER.role === "viewer") continue;
      if (["#/r/partners", "#/r/relations", "#/r/forecast", "#/r/board"].includes(href) && !["admin", "accountant"].includes(USER.role)) continue;
      if (href === "#/r/csr" && USER.role === "viewer") continue;
      if (["#/r/yearcheck", "#/r/riskmap"].includes(href) && !["admin", "accountant"].includes(USER.role)) continue;
      links.push(h("a", { href, "data-h": href }, l, NEWNAV.has(href) ? h("span", { class: "newpill" }, "New") : null));
    }
    if (!links.length) continue;
    const box = h("div", { class: "grpbox" + (st[g] === true ? " open" : ""), "data-g": g });
    const hasNew = items.some(([, href]) => NEWNAV.has(href) && links.some(a => a.dataset.h === href));
    const btn = h("button", { class: "grp", "aria-expanded": st[g] === true ? "true" : "false", onclick: () => { const o = box.classList.toggle("open"); btn.setAttribute("aria-expanded", o); const x = navState.get(); x[g] = o; navState.set(x); } }, g, hasNew ? h("span", { class: "newpill" }, "New") : null);
    box.append(btn, h("div", { class: "items" }, ...links)); boxes.push(box); nav.append(box);
  }
  find.addEventListener("input", () => {
    const q = find.value.trim().toLowerCase();
    boxes.forEach(b => { let any = false; b.querySelectorAll("a").forEach(a => { const m = !q || a.textContent.toLowerCase().includes(q); a.style.display = m ? "" : "none"; any = any || m; }); b.style.display = any ? "" : "none"; if (q) b.classList.add("open"); });
  });
  find.addEventListener("keydown", e => { if (e.key === "Enter") { const a = [...nav.querySelectorAll("a")].find(x => x.style.display !== "none"); if (a) { location.hash = a.getAttribute("href"); find.value = ""; find.dispatchEvent(new Event("input")); find.blur(); } } });
  return nav;
}
if (!window._navKey) { window._navKey = true; document.addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "")) { const f = $(".navfind"); if (f) { e.preventDefault(); f.focus(); } } }); }
function shell() {
  const app = $("#app"); app.replaceChildren();
  const main = h("main", { class: "main", id: "main" });
  app.append(h("div", { class: "shell" }, buildNav(), main));
}
function refreshSide() { const old = $(".side"); if (old) { old.replaceWith(buildNav()); setActive(); } }
function setActive() {
  const hh = location.hash || "#/dashboard";
  document.querySelectorAll(".side a").forEach(a => { const on = a.dataset.h === hh; a.classList.toggle("on", on); if (on) { const bx = a.closest(".grpbox"); if (bx) { bx.classList.add("open"); const b = bx.querySelector(".grp"); if (b) b.setAttribute("aria-expanded", "true"); } } });
}
function head(title, sub, ...right) {
  return h("div", { class: "top" }, h("div", {}, h("h1", {}, title), sub ? h("div", { class: "sub" }, sub) : null),
    h("div", { class: "userbox noprint" }, ...right, typeof bellButton === "function" ? bellButton() : null, typeof accountMenu === "function" ? accountMenu() : null));
}
function changePw() {
  const o = h("input", { type: "password" }), n = h("input", { type: "password" });
  const close = modal("Change password", h("div", {}, h("label", {}, "Current password"), o, h("label", { style: "margin-top:8px" }, "New password (8+ characters)"), n,
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"), h("button", { class: "btn pri", onclick: async () => { if (await must(() => post("/password", { old: o.value, new: n.value }))) { close(); toast("Password changed"); } } }, "Save"))));
}
async function route() {
  if (!USER || !META) return;
  const main = $("#main"); if (!main) return;
  $("#print-root").replaceChildren(); document.body.classList.remove("ov");
  setActive();
  const [, kind, arg] = (location.hash || "#/dashboard").split("/");
  if (window.OFFLINE && !(kind === "r" && ["field", "fieldact", "fieldclaim", "fieldpeople"].includes(arg))) return main.replaceChildren(head("Needs a network"), h("div", { class: "card" }, "This page needs a network connection. ", h("a", { href: "#/r/field" }, "Open the field app")));
  main.replaceChildren(h("div", { class: "empty" }, "Loading…")); if (typeof refreshBadge === "function") refreshBadge();
  try {
    let node;
    if (kind === "dashboard" || !kind) node = await viewDashboard();
    else if (kind === "t" && META.tables[arg]) node = await viewRegister(arg);
    else if (kind === "r") node = await ({ donors: viewDonorInsights, projects: viewProjectBoard, payroll: viewPayroll, grants: viewGrantDash, funds: viewFundDash, trustee: viewTrustee, budget: viewBudget, birthdays: viewBirthdays, impact: viewImpact, allprojects: viewAllProjects, formats: viewFormats, automation: viewAutomation, bank: viewBank, field: viewFieldHome, fieldpeople: viewField, fieldact: viewFieldAct, fieldclaim: viewFieldClaim, gallery: viewGallery, claims: viewClaims, cards: viewCards, pack: viewPack, inbox: viewInbox, promises: viewPromises, lapse: viewLapse, journey: viewJourney, dups: viewDups, csr: viewCsr, weekly: viewWeekly, partners: viewPartners, yearcheck: viewYearCheck, social: viewSocial, yearplan: viewYearPlan, proposal: viewProposal, riskmap: viewRiskMap, help: viewHelp, forecast: viewForecast, relations: viewRelations, board: viewBoard, followups: viewFollowups, messages: viewMessages }[arg] || (() => h("div", {}, "Not found")))();
    else if (kind === "a") node = await ({ branding: viewBranding, settings: viewSettings, lists: viewLists, users: viewUsers, audit: viewAudit, auditlog: viewAuditLog }[arg] || (() => h("div", {}, "Not found")))();
    else node = h("div", { class: "empty" }, "Page not found");
    if (kind === "dashboard" && USER.role === "admin" && META.settings.setup_done !== "Yes" && node.querySelector) node.prepend(h("div", { class: "card noprint", style: "margin-bottom:12px;border-color:var(--brand)" }, h("b", {}, "Finish setting up your software. "), "Add your name, logo and colour, then mark setup complete. ", h("a", { href: "#/a/branding" }, "Open Branding & setup →")));
    if (window.OFFLINE && node.prepend) node.prepend(offlineBanner());
    main.replaceChildren(node);
    if (typeof whyBox === "function") { const wb = whyBox(); const t = main.querySelector(".top"); if (wb) (t ? t.after(wb) : main.prepend(wb)); }
  } catch (e) { main.replaceChildren(head("Something went wrong"), h("div", { class: "card" }, e.message)); }
}
async function boot() {
  try {
    await loadBrand();
    const me = await get("/me");
    if (!me.user) return showLogin();
    USER = me.user;
    if (USER.need2fa && !USER.must_change) { META = { roles: {}, settings: {}, tables: {} }; return forceTwoStep(); }
    if (USER.must_change) { META = { roles: {}, settings: {}, tables: {} }; $("#app").replaceChildren(); return forcePassword(); }
    META = await get("/meta");
    applyBrand({ product: META.settings.brand_product, color: META.settings.brand_color, logo: META.settings.brand_logo_ver ? "/api/public/logo?v=" + META.settings.brand_logo_ver : "" });
    shell(); window.onhashchange = route; route();
    if (typeof snapshotForOffline === "function") snapshotForOffline();
  } catch (e) { if (e && e.status === 0) { if (typeof offlineBoot === "function" && await offlineBoot()) return; if (typeof offlineScreen === "function") return offlineScreen(); } showLogin(); }
}
const reload = () => route();

/* ---------------- generic register ---------------- */
const BADGE = { Active: "green", Running: "green", "On time": "green", "On pace": "green", OK: "green", Repeat: "green", Receipt: "green", Completed: "blue", Closed: "grey", Planned: "grey", Approved: "blue", Started: "blue", Reporting: "amber",
  "Ending soon": "amber", Slow: "amber", Due: "amber", New: "blue", "One gift": "grey", "Past end": "red", Over: "red", "Below zero": "red", Dropped: "red", Payment: "amber", P: "green", A: "red", H: "amber", L: "blue",
  General: "green", Restricted: "amber", Corpus: "blue", sent: "green", failed: "red",
  Paused: "grey", Ended: "grey", Enrolled: "blue", Assessed: "blue", "Service started": "blue", "Service given": "green", "Follow-up visit": "grey", "Milestone reached": "amber", "Outcome achieved": "green", Referred: "grey", Exited: "grey", "Dropped out": "red" };
function cell(v, fmt, row) {
  switch (fmt) {
    case "money": return [money(v), "n"]; case "int": case "num": return [num(v), "n"]; case "pct": return [pct(v), "n"]; case "date": return [fd(v), ""];
    case "days": return [v == null ? "–" : (v < 0 ? `${-v} days late` : v + " days"), "n"];
    case "yn": return [v === "Y" ? h("span", { class: "badge b-green" }, "Yes") : v === "N" ? h("span", { class: "badge b-amber" }, "No") : "", ""];
    case "badge": return [v ? h("span", { class: "badge b-" + (BADGE[v] || "grey") }, v) : "", ""];
    default: return [v ?? "", ""];
  }
}
const _opts = {};
async function refOptions(tbl) { return _opts[tbl] = await get("/options/" + tbl); }

async function viewRegister(name) {
  const spec = META.tables[name];
  let rows = await get("/t/" + name), q = "", sort = null, shown = 150, srv = null, srvTimer = 0;
  const CAP = 5000, capped = () => rows.length >= CAP;
  const body = h("div", { class: "tablewrap" });
  const info = h("span", { class: "sub" });
  const search = h("input", { type: "search", placeholder: "Search…", "aria-label": "Search", oninput: e => { q = e.target.value.toLowerCase(); shown = 150; srv = null; draw(); clearTimeout(srvTimer); if (q && capped()) srvTimer = setTimeout(async () => { const mine = q; try { const r = await get("/t/" + name + "?q=" + encodeURIComponent(e.target.value)); if (mine === q) { srv = r; draw(); } } catch (er) { /* keep local results */ } }, 300); } });
  const filt = () => !q ? rows : srv ? srv : rows.filter(r => spec.cols.some(c => String(r[c[0]] ?? "").toLowerCase().includes(q)));
  function draw() {
    let list = filt();
    if (sort) list = [...list].sort((a, b) => { const x = a[sort.k], y = b[sort.k]; const c = (typeof x === "number" && typeof y === "number") ? x - y : String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true }); return sort.d * c; });
    const numeric = new Set(["money", "int", "num", "pct", "days"]);
    const t = h("table", { class: "rstack" }, h("thead", {}, h("tr", {}, ...spec.cols.map(c => h("th", { class: numeric.has(c[2]) ? "n" : "", onclick: () => { sort = { k: c[0], d: sort && sort.k === c[0] ? -sort.d : 1 }; draw(); }, "aria-sort": sort && sort.k === c[0] ? (sort.d > 0 ? "ascending" : "descending") : "none" }, c[1] + (sort && sort.k === c[0] ? (sort.d > 0 ? " ▲" : " ▼") : ""))), h("th", {}, ""))),
      h("tbody", {}, ...list.slice(0, shown).map(r => h("tr", { class: "click", onclick: () => openForm(name, r) }, ...spec.cols.map(c => { const [v, cl] = cell(r[c[0]], c[2], r); return h("td", { class: cl, "data-label": c[1] }, v); }),
        h("td", { class: "acts" }, ...rowActions(name, r))))));
    const sums = spec.cols.filter(c => c[2] === "money" && !["balance", "spent", "in_hand"].includes(c[0]) || ["amount"].includes(c[0]));
    body.replaceChildren(list.length ? t : h("div", { class: "empty" }, rows.length ? "Nothing matches your search." : "No records yet. " + (can(name) ? "Click “Add” to create the first one." : "")));
    if (list.length > shown) body.append(h("div", { class: "empty" }, h("button", { class: "btn", onclick: () => { shown += 300; draw(); } }, `Show more (${list.length - shown} left)`)));
    const mc = spec.cols.find(c => c[0] === "amount" && c[2] === "money");
    info.textContent = srv ? `${list.length} found in all records` : capped() ? `Latest ${list.length.toLocaleString("en-IN")} shown. Type in Search to find older records.` : `${list.length} of ${rows.length} rows` + (mc ? ` · total ${money(list.reduce((s, r) => s + (r.amount || 0), 0))}` : "");
  }
  draw();
  const refresh = async () => { rows = await get("/t/" + name); draw(); };
  window._refreshRegister = refresh;
  const bar = h("div", { class: "bar noprint" }, search, info, h("span", { class: "grow" }),
    h("a", { class: "btn", href: `/api/export/${name}.csv`, download: "" }, "Export CSV"),
    can(name) ? h("button", { class: "btn", onclick: () => importDialog(name, refresh) }, "Import CSV") : null,
    can(name) ? h("button", { class: "btn pri", onclick: () => openForm(name, null) }, "+ Add") : null);
  return h("div", { class: "printable" }, head(spec.label, spec.hint || (can(name) ? "Click a row to edit it." : "You can view this register but not change it.")), bar, body);
}
function rowActions(name, r) {
  const a = [], btn = (l, f) => h("button", { class: "btn sm", onclick: e => { e.stopPropagation(); f(); } }, l);
  const acts = (META.tables[name].actions || []).concat(name === "donors" ? ["statement"] : []);
  if (acts.includes("docfile")) a.push(...docFileAction(r));
  if (acts.includes("receipt")) a.push(btn("Receipt", () => showPrint("receipt", r.id)));
  if (acts.includes("statement")) a.push(btn("Statement", () => showPrint("statement", r.id)));
  if (acts.includes("voucher")) a.push(btn("Voucher", () => showPrint("voucher", r.id)));
  if (acts.includes("utilisation")) a.push(btn("Utilisation", () => showPrint("utilisation", r.id)));
  if (acts.includes("activity_report")) a.push(btn("Report", () => showPrint("activity", r.id)));
  if (acts.includes("eventnote")) a.push(btn("Thank-you note", async () => { const x = await must(() => get(`/partners/event-note/${r.id}`)); if (x) modal("Note for " + (x.partner || "the company"), h("div", {}, h("textarea", { rows: 12, readonly: true, onfocus: e => e.target.select() }, x.note), x.status !== "Done" ? h("div", { class: "hint" }, "This event is not marked Done yet, so check the numbers before sending.") : null, h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: () => copyText(x.note) }, "Copy")))); }));
  if (acts.includes("print_record")) a.push(btn("Print", () => pickFormat(r.id)));
  if (name === "donors") a.push(btn("Timeline", () => showTimeline(r.id)));
  if (name === "donors" && ["admin", "accountant"].includes(USER.role)) a.push(btn("Giving page", () => donorPageDialog(r)));
  if (name === "partner_events" && can(name)) a.push(btn("People", () => eventPeopleDialog(r)));
  if (name === "donations" && ["admin", "accountant"].includes(USER.role)) a.push(btn("Send…", () => sendReceipt(r)));
  if (acts.includes("mark_done") && can(name)) a.push(btn("Mark done", async () => { if (await must(() => post(`/compliance/${r.id}/done`))) { toast("Marked done"); window._refreshRegister && window._refreshRegister(); } }));
  if (acts.includes("convert") && can(name) && r.status === "New") a.push(btn("Make donor", async () => { const x = await must(() => post(`/pledges/${r.id}/convert`)); if (x) { toast(x.existing ? "Already a donor; linked" : "Donor created"); window._refreshRegister && window._refreshRegister(); } }));
  return a;
}
function pickFormat(rid) {
  const sel = h("select", {}, ...META.formats.map(f => h("option", { value: f.name }, f.name)));
  const close = modal("Print which format?", h("div", {}, sel, h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"), h("button", { class: "btn pri", onclick: () => { close(); showPrint("record", rid, sel.value); } }, "Preview"))));
}
async function fieldInput(f, val) {
  const t = f.t; let el;
  if (t === "area") el = h("textarea", { rows: 3 }, val ?? "");
  else if (t === "date") el = h("input", { type: "date", value: val || "" });
  else if (t === "int" || t === "num") el = h("input", { type: "number", min: 0, step: t === "int" ? 1 : "any", value: val ?? "" });
  else if (t.startsWith("enum:")) { el = h("select", {}, h("option", { value: "" }, "—"), ...t.slice(5).split(",").map(o => h("option", { value: o, selected: o === val }, o))); }
  else if (t.startsWith("ref:")) { const opts = await refOptions(t.slice(4)); el = h("select", {}, h("option", { value: "" }, "— choose —"), ...opts.map(o => h("option", { value: o.id, selected: o.id === val }, o.label))); }
  else if (t.startsWith("list:")) { const id = "dl_" + f.k; el = h("input", { list: id, value: val ?? "", autocomplete: "off" }); const old = document.getElementById(id); if (old) old.remove(); document.body.append(h("datalist", { id }, ...(META.lists[t.slice(5)] || []).map(v => h("option", { value: v })))); }
  else el = h("input", { value: val ?? "" });
  return el;
}
async function openForm(name, row, defaults, after) {
  row = row && row.id ? row : null;
  const spec = META.tables[name], editing = !!row, writable = can(name);
  if (name === "cash_book" && row && row.source) return toast("This entry was posted from " + row.source.split(":")[0].replace("_", " ") + ". Edit it there.", true);
  const form = h("div", { class: "form" }), inputs = {};
  let lastGroup = null;
  for (const f of spec.fields) {
    if (f.group && f.group !== lastGroup) { form.append(h("div", { class: "grouphead" }, f.group)); lastGroup = f.group; }
    let v = row ? row[f.k] : defaults && f.k in defaults ? defaults[f.k] : (f.t === "date" && ["date", "date_joined"].includes(f.k) ? asofISO() : null);
    if (!row && !(defaults && f.k in defaults) && f.t.startsWith("enum:")) { const o = f.t.slice(5).split(","); if (["Y", "N"].every(x => o.includes(x))) v = ["active", "bill_kept", "wishes"].includes(f.k) ? "Y" : "N"; else if (f.k === "status") v = "Active"; else if (f.k === "attendance") v = "P"; else if (f.k === "type" && name === "cash_book") v = "Payment"; else if (f.k === "fund_type") v = "General"; else if (f.k === "pay_type") v = "Monthly"; }
    const el = await fieldInput(f, v); inputs[f.k] = el;
    if (el.disabled !== undefined) el.disabled = !writable;
    form.append(h("div", { class: ["area"].includes(f.t) || f.k === "name" && false ? "full" : (f.t === "area" ? "full" : "") }, h("label", { class: f.req ? "req" : "" }, f.l), el));
  }
  const collect = () => { const o = {}; for (const f of spec.fields) { const el = inputs[f.k]; o[f.k] = el.value; } return o; };
  const save = async () => {
    const r = await must(() => editing ? put(`/t/${name}/${row.id}`, collect()) : post(`/t/${name}`, collect()));
    if (r) { close(); toast(editing ? "Saved" : "Added"); if (after) after(r); if (window._refreshRegister) window._refreshRegister(); delete _opts[""]; Object.keys(_opts).forEach(k => delete _opts[k]); }
  };
  const acts = h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, writable ? "Cancel" : "Close"),
    writable && editing ? h("button", { class: "btn danger", onclick: () => confirmBox("Delete this record? This cannot be undone.", async () => { if (await must(() => del(`/t/${name}/${row.id}`))) { close(); toast("Deleted"); window._refreshRegister && window._refreshRegister(); } }) }, "Delete") : null,
    writable ? h("button", { class: "btn pri", onclick: save }, editing ? "Save changes" : "Add") : null);
  const close = modal((editing ? "Edit · " : "Add · ") + spec.label.replace(/s$/, ""), h("div", {}, form, acts), { wide: true });
}
function importDialog(name, done) {
  const spec = META.tables[name];
  const ta = h("textarea", { rows: 8, placeholder: "Paste CSV here, or choose a file below", style: "font-family:monospace" });
  const file = h("input", { type: "file", accept: ".csv,text/csv", onchange: async e => { const f = e.target.files[0]; if (f) ta.value = await f.text(); } });
  const out = h("div", { class: "hint" });
  const close = modal("Import CSV · " + spec.label, h("div", {}, h("p", { class: "hint" }, "First row = column names, exactly as on the Add form: ", spec.fields.map(f => f.l).join(", "), ". Choice columns (like Donor or Project) take the code or name. If any row has a problem, nothing is imported."), ta, file, out,
    h("div", { class: "actions" }, h("a", { class: "btn", href: `/api/import-template/${name}.csv`, download: "" }, "Blank template"), h("button", { class: "btn", onclick: () => close() }, "Cancel"), h("button", { class: "btn", onclick: async () => {
      const r = await must(() => post("/import/" + name, { csv: ta.value, dry: true })); if (!r) return;
      if (r.errors.length) out.replaceChildren(h("b", { style: "color:#c23b3a" }, `${r.total_errors} problem(s) found. Nothing was saved:`), h("ul", {}, ...r.errors.map(e => h("li", {}, e))));
      else out.replaceChildren(h("b", { style: "color:#16794a" }, `Looks good: ${r.would_import} row(s) can be imported. Nothing was saved yet. Press Import to save them.`));
    } }, "Check file first"), h("button", { class: "btn pri", onclick: async () => {
      const r = await must(() => post("/import/" + name, { csv: ta.value })); if (!r) return;
      if (r.errors.length) out.replaceChildren(h("b", { style: "color:#c23b3a" }, `Nothing imported — ${r.total_errors} problem(s):`), h("ul", {}, ...r.errors.map(e => h("li", {}, e))));
      else { close(); toast(`${r.imported} rows imported`); done(); }
    } }, "Import"))), { wide: true });
}

/* ---------------- admin views ---------------- */
async function viewSettings() {
  const s = (await get("/meta")).settings; META.settings = s;
  const groups = [
    ["Your organisation (prints on every document)", [["org_name", "Organisation name"], ["org_pan", "Organisation PAN"], ["org_csr1", "CSR-1 registration no."], ["org_darpan", "NGO Darpan ID"], ["org_fcra", "FCRA no. (if any)"], ["org_12a", "12A registration no."], ["org_80g", "80G approval no."], ["org_head", "Secretary or head"], ["org_address", "Address"], ["org_phone", "Phone"], ["org_email", "Email"], ["org_reg", "Registration nos, if any"], ["org_tagline", "Line under the name"], ["org_upi", "UPI ID"]]],
    ["Tax information (your own entries; check with your CA)", [["gst_registered", "GST registered?", ["No", "Yes"]], ["gst_pct", "GST %"], ["gst_limit", "GST limit"], ["taxable_receipts", "Taxable receipts a year"]]],
    ["Rules", [["repeat_gifts", "Repeat donor from gifts"], ["grant_slow_gap", "Mark grant Slow when used % is behind time % by (0.3 = 30 points)"], ["ending_soon_days", "Project ending soon within (days)"], ["extra_hour_rate", "Extra hour rate (₹)"], ["travel_per_km", "Travel paid back per km (₹)"], ["working_days", "Working days a month (planning)"], ["fy_start_month", "Financial year starts in month number"], ["asof_override", "Freeze today's date (YYYY-MM-DD, blank = real today)"]]],
    ["Email and birthday wishes (use your own mail account; Gmail needs an app password)", [["smtp_host", "Mail server (e.g. smtp.gmail.com)"], ["smtp_port", "Port (587 or 465)"], ["smtp_security", "Security", ["starttls", "ssl", "none"]], ["smtp_user", "Mail username"], ["smtp_password", "Mail password (leave blank to keep the saved one)", "password"], ["smtp_from", "Send from (email address)"], ["birthday_auto", "Send birthday wishes automatically every day", ["No", "Yes"]], ["birthday_send_hour", "…after this hour (0-23, server time)"], ["birthday_subject", "Wish subject. {name} {org}"], ["birthday_body", "Wish message. Use {name} {org} {contact} {age}", "area"]]],
    ["Official WhatsApp and SMS (your own provider account; see the help below)", [["wa_provider", "WhatsApp provider", ["None", "Meta", "Twilio", "Custom"]], ["wa_phone_id", "WhatsApp: Meta phone number ID"], ["wa_token", "WhatsApp: Meta access token", "password"], ["wa_lang", "WhatsApp template language (e.g. en, hi, en_US)"],
      ["sms_provider", "SMS provider", ["None", "MSG91", "Twilio", "Custom"]], ["sms_authkey", "SMS: MSG91 auth key", "password"], ["twilio_sid", "Twilio account SID"], ["twilio_token", "Twilio auth token", "password"], ["twilio_wa_from", "Twilio WhatsApp number (e.g. +14155238886)"], ["twilio_sms_from", "Twilio SMS number or sender"],
      ["custom_url", "Custom provider: address (https://…)"], ["custom_headers", "Custom provider: headers as JSON", "password"], ["custom_body", "Custom provider: body as JSON using {to} {message} {template} {p1} {p2}", "area"]]],
    ["Automation: receipts, digest, alerts, reports, backup", [["auto_receipt_email", "Email a receipt + thank-you automatically when a donation is saved (needs donor email)", ["No", "Yes"]], ["thanks_message", "Thank-you message ({name} {amount} {receipt} {org} {contact})", "area"], ["digest_auto", "Send the morning digest by email", ["No", "Yes"]], ["digest_to", "Digest and alert recipients (emails, comma separated)"], ["digest_hour", "Send digest from hour (0-23)"], ["deadline_alerts_auto", "Email grant report and compliance deadline alerts", ["No", "Yes"]], ["grant_alert_days", "Alert when this many days are left (e.g. 30,15,7)"], ["trustee_report_auto", "Email monthly trustee report", ["No", "Yes"]], ["trustee_emails", "Trustee emails (comma separated)"], ["report_day", "Send reports on or after day of month"], ["impact_auto", "Email each donor a quarterly impact report", ["No", "Yes"]], ["backup_auto", "Automatic daily backup", ["Yes", "No"]], ["backup_encrypt", "Lock automatic backups with a password", ["No", "Yes"]], ["backup_password", "Backup password (8+ characters; keep a copy somewhere safe)", "password"], ["backup_keep", "Keep this many daily backups"], ["backup_copy_dir", "Also copy each backup to this folder (a pen drive or synced folder)"],
      ["weekly_auto", "Send the manager weekly summary on Mondays", ["No", "Yes"]], ["weekly_to", "Weekly summary emails (blank = same as the digest recipients)"], ["weekly_wa_to", "Weekly summary WhatsApp numbers (optional, comma separated)"], ["weekly_wa_template", "Approved WhatsApp template for the weekly summary (one variable)"],
      ["commit_remind_auto", "Email donors a reminder before a regular gift is due", ["No", "Yes"]], ["commit_remind_days", "Remind this many days before the due date"], ["lapse_factor", "A donor is slipping after this many times their usual gap (e.g. 1.5)"], ["stale_journey_days", "Flag people with no recorded step for this many days"]]],
    ["Money planning (cash forecast, key relationships)", [["core_monthly_cost", "Core monthly cost in ₹ (rent, salaries, running costs). 0 = use the last 3 months' average"], ["reserve_months", "Keep free cash worth this many months of cost (e.g. 3)"], ["major_donor_min", "A major donor has given at least ₹"]]],
    ["Receiving replies (inbox and STOP)", [["public_url", "Public web address of this software (https://…)"], ["wa_app_secret", "WhatsApp (Meta): App Secret", "password"], ["wa_verify_token", "WhatsApp (Meta): Verify token", "password"], ["inbound_token", "Other providers: webhook token", "password"],
      ["inbound_stop_reply", "Send an automatic confirmation when someone replies STOP", ["Yes", "No"]], ["inbound_stop_text", "Confirmation text"]]],
    ["Security", [["require_2fa_admin", "Require two-step sign-in (a code from the phone) for administrators", ["No", "Yes"]]]],
    ["Public Donate page (needs your UPI ID above)", [["donate_page", "Switch on the Donate page at /donate.html", ["No", "Yes"]], ["donate_message", "Message shown on the page", "area"]]],
    ["Your CA and auditor (fill in later; leave blank until you have them)", [["ca_name", "CA name"], ["ca_firm", "CA firm"], ["ca_phone", "CA phone"], ["ca_email", "CA email"], ["ca_membership_no", "CA membership no"], ["auditor_name", "Auditor name (if different)"], ["auditor_phone", "Auditor phone"], ["ca_notes", "Notes about your CA", "area"]]],
    ["Public pages (transparency and sponsor outcomes)", [["public_transparency", "Switch on the public transparency page at /transparency.html", ["No", "Yes"]], ["transparency_note", "A short note shown at the top of that page", "area"], ["outcome_intro", "Sentence above the outcome list on the Donate page"]]],
    ["Donor impact report", [["reporting_period", "Reporting period"], ["prepared_by", "Report prepared by"], ["designation", "Designation"], ["green_from", "Green from (%)"], ["light_from", "Light green from (%)"], ["yellow_from", "Yellow from (%) – below is red"], ["money_ahead", "Money ahead of work by (points)"], ["time_ahead", "Time ahead of work by (points)"]]]];
  const ins = {}, cards = [];
  for (const [t, fs] of groups) {
    const g = h("div", { class: "inputgrid" });
    for (const [k, l, opts] of fs) {
      const el = Array.isArray(opts) ? h("select", {}, ...opts.map(o => h("option", { value: o, selected: s[k] === o }, o))) : opts === "area" ? h("textarea", { rows: 5 }, s[k] ?? "") : opts === "password" ? h("input", { type: "password", autocomplete: "new-password", placeholder: s[k + "_set"] === "Yes" ? "(saved; leave blank to keep)" : "" }) : h("input", { value: s[k] ?? "" });
      ins[k] = el; el.dataset.k = k; g.append(h("div", { class: opts === "area" ? "full" : "", style: opts === "area" ? "grid-column:1/-1" : "" }, h("label", {}, l), el));
    }
    const isMail = t.startsWith("Email"), isGw = t.startsWith("Official WhatsApp"), isIn = t.startsWith("Receiving replies");
    cards.push(h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, t), g, isMail ? h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => testMail() }, "Save, then send a test email")) : null, isGw ? gatewayHelp(() => save()) : null, isIn ? inboxHelp() : null));
  }
  const save = async () => { const o = {}; for (const k in ins) o[k] = ins[k].value; if (await must(() => put("/settings", o))) { toast("Settings saved"); META = await get("/meta"); refreshSide(); return true; } };
  const testMail = async () => {
    if (!(await save())) return;
    const to = h("input", { type: "email", placeholder: "you@example.org" });
    const close = modal("Send a test email", h("div", {}, h("label", {}, "Send to"), to, h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"),
      h("button", { class: "btn pri", onclick: async () => { if (await must(() => post("/email/test", { to: to.value }))) { close(); toast("Test email sent"); } } }, "Send"))));
  };
  return h("div", {}, head("Settings", "Everything here is yours to set. Rates and limits are samples until you change them."), ...cards, h("button", { class: "btn pri", onclick: save }, "Save settings"));
}
async function viewLists() {
  const all = await get("/lists/all"), kinds = [...new Set([...all.map(a => a.kind), "donor_type", "purpose", "mode", "city", "stage", "village", "service", "activity", "age_group", "role", "duty", "spend_head", "payment_head", "receipt_head", "people_group", "result_unit", "budget_group", "unit"])];
  const LAB = { relation: "Contact types", donor_type: "Donor types", purpose: "Donation purposes", mode: "Payment modes", city: "Cities", stage: "Project stages", village: "Villages or wards", service: "Services", activity: "Activities", age_group: "Age groups", role: "Team roles", duty: "Volunteer duties", spend_head: "Spending heads", payment_head: "Payment heads", receipt_head: "Receipt heads", people_group: "People groups", result_unit: "Result units", budget_group: "Budget groups", unit: "Units" };
  const wrap = h("div", { class: "grid2" });
  for (const k of kinds) {
    const inp = h("input", { placeholder: "Add a value…" });
    const add = async () => { if (inp.value.trim() && await must(() => post("/lists", { kind: k, value: inp.value }))) { META = await get("/meta"); route(); } };
    inp.addEventListener("keydown", e => e.key === "Enter" && add());
    wrap.append(h("div", { class: "card" }, h("h3", {}, LAB[k] || k), h("div", {}, ...all.filter(a => a.kind === k).map(a => h("span", { class: "badge b-grey", style: "margin:2px;padding:3px 8px" }, a.value, " ", h("a", { href: "#", title: "Remove", onclick: async e => { e.preventDefault(); if (await must(() => del("/lists/" + a.id))) { META = await get("/meta"); route(); } } }, "×")))), h("div", { class: "bar", style: "margin-top:8px" }, inp, h("button", { class: "btn sm", onclick: add }, "Add"))));
  }
  return h("div", {}, head("Dropdown lists", "These fill the choices on forms. Removing a value does not change records that already use it."), wrap);
}
async function viewUsers() {
  const users = await get("/users");
  const t = h("table", {}, h("thead", {}, h("tr", {}, ...["Username", "Name", "Role", "Two-step", "Active", ""].map(x => h("th", {}, x)))), h("tbody", {}, ...users.map(u => {
    const sel = h("select", { onchange: async () => { if (await must(() => put("/users/" + u.id, { role: sel.value }))) toast("Role updated"); else route(); } }, ...Object.entries(META.roles).map(([k, l]) => h("option", { value: k, selected: k === u.role }, l)));
    return h("tr", {}, h("td", {}, u.username), h("td", {}, u.name), h("td", {}, sel), h("td", {}, u.totp ? h("span", { class: "badge b-green" }, "On") : h("span", { class: "badge b-grey" }, "Off"), u.totp ? [" ", h("button", { class: "btn sm", onclick: () => confirmBox("Switch off two-step sign-in for " + u.username + "? Use this if they lost their phone and backup codes. They will be signed out.", async () => { if (await must(() => post("/users/" + u.id + "/reset2fa"))) { toast("Reset"); route(); } }, "Reset") }, "Reset")] : null), h("td", {}, u.active ? h("span", { class: "badge b-green" }, "Active") : h("span", { class: "badge b-red" }, "Locked")),
      h("td", {}, h("button", { class: "btn sm", onclick: async () => { if (await must(() => put("/users/" + u.id, { active: u.active ? 0 : 1 }))) route(); } }, u.active ? "Lock" : "Unlock"), " ",
        h("button", { class: "btn sm", onclick: () => { const p = h("input", { type: "text", placeholder: "New temporary password" }); const c = modal("Reset password · " + u.username, h("div", {}, p, h("div", { class: "hint" }, "They must change it at next sign-in."), h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: async () => { if (await must(() => put("/users/" + u.id, { password: p.value }))) { c(); toast("Password reset"); } } }, "Reset")))); } }, "Reset password")));
  })));
  const un = h("input", { placeholder: "username" }), nm = h("input", { placeholder: "Full name" }), pw = h("input", { placeholder: "Temporary password (8+)" }), rl = h("select", {}, ...Object.entries(META.roles).map(([k, l]) => h("option", { value: k }, l)));
  return h("div", {}, head("Users", "Administrators manage who can sign in and what they can change."), h("div", { class: "tablewrap", style: "margin-bottom:14px" }, t),
    h("div", { class: "card" }, h("h2", {}, "Add a user"), h("div", { class: "inputgrid" }, h("div", {}, h("label", {}, "Username"), un), h("div", {}, h("label", {}, "Name"), nm), h("div", {}, h("label", {}, "Role"), rl), h("div", {}, h("label", {}, "Password"), pw)),
      h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: async () => { if (await must(() => post("/users", { username: un.value, name: nm.value, role: rl.value, password: pw.value }))) { toast("User added"); route(); } } }, "Add user"))));
}
async function viewAudit() {
  const a = await get("/audit"), bk = await backupCard();
  return h("div", {}, head("Backup & restore", "Copies of your data, password-protected backups, restore, and the last 300 changes (full search is under Audit trail)."),
    h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, "Backup"), h("p", {}, "Download the whole database as one plain file (not password-protected; use the locked version below for a pen drive or email). Keep copies somewhere safe (another computer or drive)."), h("a", { class: "btn pri", href: "/api/backup" }, "Download backup now"), " ", h("button", { class: "btn", onclick: async () => { const r = await must(() => post("/automation/run/backup")); if (r) toast(r.note, !r.ok); } }, "Save a copy on the server now"), h("p", { class: "hint" }, "Last automatic backup: " + (META.settings.last_backup || "none yet"))),
    bk,
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["When", "Who", "Action", "Register", "Row", "Detail"].map(x => h("th", {}, x)))), h("tbody", {}, ...a.map(r => h("tr", {}, h("td", {}, r.ts.replace("T", " ")), h("td", {}, r.user), h("td", {}, r.action), h("td", {}, r.tbl), h("td", {}, r.row_id), h("td", { style: "max-width:420px;overflow:hidden;text-overflow:ellipsis" }, r.detail)))))));
}
