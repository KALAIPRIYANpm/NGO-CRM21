/* Dashboards, reports, planning tools. */
"use strict";
const C = { blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", yellow: "#eda100", magenta: "#e87ba4", green: "#008300", violet: "#6250d6", red: "#e34948" };
const kpi = (l, v, s, cls) => h("div", { class: "card kpi " + (cls || "") }, h("div", { class: "l" }, l), h("div", { class: "v" }, v), h("div", { class: "s" }, s || " "));
const kvTable = rows => h("table", { class: "kv" }, h("tbody", {}, ...rows.filter(r => r).map(r => h("tr", {}, h("td", {}, r[0]), h("td", {}, r[1])))));
const mkTable = (cols, rows, opts = {}) => h("div", { class: "tablewrap" }, rows.length ? h("table", {}, h("thead", {}, h("tr", {}, ...cols.map(c => h("th", { class: c[2] && c[2] !== "text" && c[2] !== "badge" ? "n" : "", style: "cursor:default" }, c[1])))),
  h("tbody", {}, ...rows.map(r => h("tr", {}, ...cols.map(c => { const [v, cl] = cell(r[c[0]], c[2], r); return h("td", { class: cl }, v); })))), opts.foot ? h("tfoot", {}, opts.foot) : null) : h("div", { class: "empty" }, "Nothing to show yet."));
const monthInput = (val, on) => h("input", { type: "month", value: val, onchange: e => e.target.value && on(e.target.value) });

/* grouped bar chart, SVG, with legend, hover tips and a table view */
function barChart(data, series, opts = {}) {
  const W = 640, H = 230, L = 52, B = 26, T = 10, R = 8, pw = W - L - R, ph = H - T - B;
  const max = Math.max(1, ...data.flatMap(d => series.map(s => d[s.key] || 0)));
  const step = Math.pow(10, Math.floor(Math.log10(max))), nice = Math.ceil(max / step) * step, top = nice > max * 1.6 ? nice - step / 2 >= max ? nice - step / 2 : nice : nice;
  const ns = "http://www.w3.org/2000/svg", el = (t, a, ...k) => { const e = document.createElementNS(ns, t); for (const [x, y] of Object.entries(a || {})) e.setAttribute(x, y); k.forEach(c => e.append(c.nodeType ? c : document.createTextNode(c))); return e; };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": opts.label || "Chart" });
  for (let i = 0; i <= 4; i++) { const v = top * i / 4, y = T + ph - ph * i / 4; svg.append(el("line", { x1: L, x2: W - R, y1: y, y2: y, stroke: "#e4e1da", "stroke-width": 1 }), el("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, v >= 100000 ? (v / 100000).toFixed(v % 100000 ? 1 : 0) + "L" : v >= 1000 ? (v / 1000) + "k" : v)); }
  const gw = pw / data.length, bw = Math.min(18, (gw - 8) / series.length - 2);
  data.forEach((d, i) => {
    const gx = L + gw * i + gw / 2 - (series.length * (bw + 2)) / 2;
    series.forEach((s, j) => { const v = d[s.key] || 0, bh = Math.max(v ? 2 : 0, ph * v / top), x = gx + j * (bw + 2), y = T + ph - bh;
      const r = el("rect", { x, y, width: bw, height: bh, fill: s.color, rx: 3 }); tip(r, `${fm(d.month)} · ${s.label}: ${money(v)}`); svg.append(r); });
    if (data.length <= 12 || i % 2 === 0) svg.append(el("text", { x: L + gw * i + gw / 2, y: H - 8, "text-anchor": "middle" }, fm(d.month)));
  });
  const box = h("div", {}, h("div", { class: "legend" }, ...series.map(s => h("span", {}, h("i", { style: `background:${s.color}` }), s.label))), svg);
  const tbl = mkTable([["month", "Month"], ...series.map(s => [s.key, s.label, "money"])], data.map(d => ({ ...d, month: fm(d.month) }))); tbl.style.display = "none";
  const tg = h("button", { class: "btn sm noprint", onclick: () => { const on = tbl.style.display === "none"; tbl.style.display = on ? "" : "none"; svg.style.display = on ? "none" : ""; tg.textContent = on ? "Show chart" : "Show table"; } }, "Show table");
  return h("div", {}, box, tbl, h("div", { style: "margin-top:4px" }, tg));
}
function hbars(items, opts = {}) {
  const max = Math.max(1, ...items.map(i => i.v));
  return h("div", {}, ...items.map(i => { const r = h("div", { class: "hbar" }, h("span", { class: "nm", title: i.l }, i.l), h("span", { class: "tr" }, h("i", { style: `width:${Math.max(1, i.v / max * 100)}%;background:${opts.color || C.blue}` })), h("span", { class: "vl" }, opts.fmt ? opts.fmt(i.v) : money(i.v))); tip(r, `${i.l}: ${opts.fmt ? opts.fmt(i.v) : money(i.v)}`); return r; }));
}
const progress = (v, color) => h("div", { class: "progress", title: pct(v) }, h("i", { style: `width:${Math.min(100, (v || 0) * 100)}%;background:${color || C.blue}` }));

/* ---------------- dashboard ---------------- */
async function viewDashboard() {
  const d = await get("/dashboard");
  const alerts = d.alerts.length ? d.alerts.map(a => h("div", { class: "alert" }, h("span", { class: "dot " + a.level }), a.text, h("a", { href: (a.link.includes("/") ? "#/" : "#/t/") + a.link }, "Open →"))) : [h("div", { class: "empty" }, "Nothing needs attention. ✔")];
  return h("div", { class: "printable" }, head("Dashboard", `${d.org} · as on ${fd(d.asof)}`, h("button", { class: "btn sm", onclick: () => window.print() }, "Print")),
    h("div", { class: "cards" },
      kpi("Fund balance", money(d.fund_balance), `General ${money(d.fund_general)}`), kpi("Receipts, this year", money(d.receipts_fy), "from 1 April"), kpi("Payments, this year", money(d.payments_fy), "from 1 April"),
      kpi("Surplus, this year", money(d.surplus_fy), "receipts − payments", d.surplus_fy < 0 ? "bad" : ""), kpi("Donations, last 12 months", money(d.gifts_12m), `${d.donors} donors`), kpi("Donations, this month", money(d.gifts_month), `avg gift ${money(d.avg_gift)}`),
      kpi("Open projects", d.open_projects, `${d.people_listed} people listed`), kpi("People reached", IN.format(d.people_reached), `${d.activities} activities`),
      kpi("Payroll, " + fm(d.payroll_month), money(d.payroll_net), `${d.staff} staff · ${d.volunteers} volunteers`), kpi("Grants in hand", money(d.grant_in_hand), `${money(d.grant_spent)} of ${money(d.grant_sanctioned)} spent`),
      kpi("Birthdays today", d.birthdays_today, `${d.birthdays_week} in the next 7 days`, d.birthdays_today ? "warn" : ""), kpi("Receipts to give", d.receipts_to_give, "donations", d.receipts_to_give ? "warn" : ""), kpi("Donors to call", d.followups_due, "follow-up due", d.followups_due ? "warn" : "")),
    h("div", { class: "grid2" }, h("div", { class: "card" }, h("h2", {}, "Needs attention"), ...alerts),
      h("div", { class: "card" }, h("h2", {}, "Money in and out, last 12 months"), barChart(d.series, [{ key: "receipts", label: "Receipts", color: C.blue }, { key: "payments", label: "Payments", color: C.orange }], { label: "Monthly receipts and payments" }))),
    h("div", { class: "grid2" }, h("div", { class: "card" }, h("h2", {}, "Top donors"), hbars(d.top_donors.map(x => ({ l: x.name, v: x.total })))),
      h("div", { class: "card" }, h("h2", {}, "Gifts by purpose"), hbars(d.by_purpose.map(x => ({ l: x.purpose, v: x.total })), { color: C.aqua })),
      h("div", { class: "card" }, h("h2", {}, "Call today"), d.call_today.length ? mkTable([["name", "Donor"], ["phone", "Phone"], ["next_followup", "Due", "date"]], d.call_today) : h("div", { class: "empty" }, "No calls due."))));
}
async function viewDonorInsights() {
  const d = await get("/report/donors");
  return h("div", { class: "printable" }, head("Donor insights", "Who gives, from where, and who to follow up."),
    h("div", { class: "cards" }, kpi("Donors", d.donors), kpi("Last 12 months", money(d.gifts_12m)), kpi("Average gift", money(d.avg_gift)), kpi("Receipts to give", d.receipts_to_give), kpi("Thank-yous due", d.thank_you_due), kpi("Follow up today", d.followups_due)),
    h("div", { class: "grid2" }, h("div", { class: "card" }, h("h2", {}, "Gifts by month"), barChart(d.series, [{ key: "donations", label: "Donations", color: C.blue }])),
      h("div", { class: "card" }, h("h2", {}, "By donor type"), hbars(d.by_type.map(x => ({ l: x.type, v: x.total })), { color: C.violet }), h("h3", { style: "margin-top:14px" }, "By city"), hbars(d.by_city.map(x => ({ l: x.city, v: x.total })), { color: C.aqua })),
      h("div", { class: "card" }, h("h2", {}, "Donor levels"), hbars(d.levels.map(x => ({ l: x.level, v: x.n })), { fmt: v => v, color: C.orange }), h("h3", { style: "margin-top:14px" }, "By fund type"), hbars(d.by_fund_type.map(x => ({ l: x.fund_type || "?", v: x.total })))),
      h("div", { class: "card" }, h("h2", {}, "Top donors"), mkTable([["name", "Donor"], ["gifts", "Gifts", "int"], ["total", "Total", "money"]], d.top_donors))));
}
async function viewProjectBoard() {
  const d = await get("/report/projects");
  const board = h("div", { class: "board" }, ...d.stages.map(st => h("div", { class: "col" }, h("h3", {}, st, h("span", {}, d.board[st].length)),
    ...d.board[st].map(p => h("div", { class: "pcard" }, h("b", {}, p.name), h("div", { class: "hint" }, [p.place, p.lead].filter(Boolean).join(" · ")), h("div", { class: "hint" }, "Reach ", pct(p.reach)), progress(p.reach, C.aqua), p.flag && p.flag !== "On time" ? h("span", { class: "badge b-" + (BADGE[p.flag] || "grey"), style: "margin-top:6px" }, p.flag) : null)))));
  const t = d.totals;
  return h("div", { class: "printable" }, head("Project board", "Every project against its stage."), h("div", { class: "cards" }, kpi("Open projects", t.open), kpi("People listed", IN.format(t.listed)), kpi("Spent", money(t.spent), "of " + money(t.budget)), kpi("Ending soon", t.ending, "", t.ending ? "warn" : "")),
    h("div", { class: "card", style: "margin-bottom:14px" }, board),
    h("div", { class: "grid2" }, h("div", { class: "card" }, h("h2", {}, "People by village"), hbars(d.village.map(x => ({ l: x.k, v: x.n })), { fmt: v => v })), h("div", { class: "card" }, h("h2", {}, "Gender"), hbars(d.gender.map(x => ({ l: x.k, v: x.n })), { fmt: v => v, color: C.magenta }), h("h3", { style: "margin-top:14px" }, "Age group"), hbars(d.age.map(x => ({ l: x.k, v: x.n })), { fmt: v => v, color: C.violet }))),
    mkTable([["name", "Project"], ["stage", "Stage", "badge"], ["people_listed", "Listed", "int"], ["target_people", "Target", "int"], ["reach", "Reach", "pct"], ["budget", "Budget", "money"], ["spent", "Spent", "money"], ["used", "Used", "pct"], ["days_left", "Days left", "int"], ["flag", "Flag", "badge"]], d.projects));
}
async function viewPayroll() {
  let month = prevMonth();
  const wrap = h("div", { class: "printable" });
  async function draw() {
    const d = await get("/report/payroll?month=" + month), t = d.totals;
    wrap.replaceChildren(head("Payroll", "Staff pay, volunteer travel paid back, advances and net payable."), h("div", { class: "bar noprint" }, "Month ", monthInput(month, m => { month = m; draw(); }), h("span", { class: "grow" }), ["admin", "accountant"].includes(USER.role) ? h("a", { class: "btn", href: "/api/export/payroll-bank.csv?month=" + month, download: "" }, "Bank upload sheet (CSV)") : null, h("button", { class: "btn", onclick: () => window.print() }, "Print")),
      h("div", { class: "cards" }, kpi("Staff", t.staff), kpi("Volunteers", t.volunteers), kpi("Due", money(t.due)), kpi("Advances", money(t.advances)), kpi("Net payable", money(t.net)), kpi("Volunteer hours", num(t.vol_hours))),
      mkTable([["code", "ID"], ["name", "Name"], ["role", "Role"], ["pay_type", "Pay type"], ["pay_rate", "Rate", "money"], ["days_present", "Days present", "num"], ["vol_hours", "Vol. hours", "num"], ["travel_paid", "Travel paid", "money"], ["due", "Due", "money"], ["advances", "Advances", "money"], ["net", "Net payable", "money"]], d.rows,
        { foot: h("tr", {}, h("td", { colspan: 8 }, "Total"), h("td", { class: "n" }, money(t.due)), h("td", { class: "n" }, money(t.advances)), h("td", { class: "n" }, money(t.net))) }),
      h("p", { class: "hint" }, "Monthly = fixed pay. Per day = rate × days present (half day = half) + extra hours. Volunteers get no pay; only travel and food paid back. Net payable = due − advances."),
      ["admin", "accountant"].includes(USER.role) ? h("div", { class: "card noprint", style: "margin-top:12px" }, h("h2", {}, "Payslips"), h("p", { class: "hint" }, "Bank account and IFSC are kept in each Team record. The bank upload sheet lists only people with money to pay."), h("div", { style: "display:flex;flex-wrap:wrap;gap:6px" }, ...d.rows.map(r => h("button", { class: "btn sm", onclick: () => showPrint("payslip", r.id, null, month) }, r.name)))) : null);
  }
  await draw(); return wrap;
}
async function viewGrantDash() {
  const { grants } = await get("/report/grants");
  const tot = k => grants.reduce((s, g) => s + g[k], 0);
  return h("div", { class: "printable" }, head("Grant dashboard", "Money received, spent and in hand against time."),
    h("div", { class: "cards" }, kpi("Grants", grants.length), kpi("Sanctioned", money(tot("sanctioned"))), kpi("Received", money(tot("received"))), kpi("Spent", money(tot("spent"))), kpi("In hand", money(tot("in_hand")))),
    h("div", { class: "grid2" }, ...grants.map(g => h("div", { class: "card" }, h("div", { style: "display:flex;justify-content:space-between;gap:8px" }, h("div", {}, h("b", {}, g.funder), h("div", { class: "hint" }, g.code + " · " + (g.project || "No project"))), cell(g.pace, "badge")[0]),
      h("div", { style: "margin-top:10px" }, h("div", { class: "hint" }, `Spent ${pct(g.used)} of ${money(g.sanctioned)}`), progress(g.used, C.blue), h("div", { class: "hint", style: "margin-top:6px" }, `Time gone ${pct(g.time_gone)}`), progress(g.time_gone, "#8a877f")),
      kvTable([["Received", money(g.received)], ["Spent", money(g.spent)], ["In hand", money(g.in_hand)], ["Report due", g.report_due ? `${fd(g.report_due)} (${cell(g.report_in_days, "days")[0]})` : "–"]]),
      h("button", { class: "btn sm noprint", onclick: () => showPrint("utilisation", g.id) }, "Utilisation certificate")))));
}
async function viewFundDash() {
  const d = await get("/report/funds");
  return h("div", { class: "printable" }, head("Fund dashboard", "Balances by fund and fund type, and the year's money in and out."),
    h("div", { class: "cards" }, ...d.by_type.map(t => kpi(t.type + " funds", money(t.balance), `opening ${money(t.opening)}`)), ...(d.gst ? [kpi("Room below GST limit", money(d.gst.room), `taxable ${money(d.gst.taxable)} of ${money(d.gst.limit)}`)] : [])),
    h("div", { class: "grid2" }, h("div", { class: "card" }, h("h2", {}, "Receipts, payments and surplus by month"), barChart(d.series, [{ key: "receipts", label: "Receipts", color: C.blue }, { key: "payments", label: "Payments", color: C.orange }])),
      h("div", { class: "card" }, h("h2", {}, "Payments by head"), hbars(d.payment_heads.map(x => ({ l: x.head, v: x.amount })), { color: C.orange }))),
    mkTable([["name", "Fund"], ["type", "Type", "badge"], ["purpose", "Purpose"], ["opening", "Opening", "money"], ["received", "Received", "money"], ["spent", "Spent", "money"], ["balance", "Balance", "money"], ["status", "Status", "badge"]], d.funds));
}
async function viewTrustee() {
  let month = prevMonth(); const wrap = h("div", { class: "printable" });
  async function draw() {
    const d = await get("/report/trustee?month=" + month), t = d.totals;
    wrap.replaceChildren(head("Trustee report", "One month: opening balance, receipts, payments and closing balance by fund."), h("div", { class: "bar noprint" }, "Month ", monthInput(month, m => { month = m; draw(); }), h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => window.print() }, "Print")),
      h("div", { class: "card", style: "margin-bottom:14px" }, h("b", {}, d.org.name), h("div", { class: "hint" }, `Trustee report for ${fm(month)}`)),
      h("div", { class: "cards" }, kpi("Opening", money(t.opening)), kpi("Receipts", money(t.receipts)), kpi("Payments", money(t.payments)), kpi("Surplus", money(t.surplus), "", t.surplus < 0 ? "bad" : ""), kpi("Closing", money(t.closing))),
      mkTable([["fund", "Fund"], ["type", "Type", "badge"], ["opening", "Opening", "money"], ["receipts", "Receipts", "money"], ["payments", "Payments", "money"], ["closing", "Closing", "money"]], d.funds, { foot: h("tr", {}, h("td", { colspan: 2 }, "Total"), ...["opening", "receipts", "payments", "closing"].map(k => h("td", { class: "n" }, money(t[k])))) }),
      h("div", { class: "grid2", style: "margin-top:14px" }, h("div", { class: "card" }, h("h2", {}, "Receipts by head"), hbars(d.receipt_heads.map(x => ({ l: x.head, v: x.amount })))), h("div", { class: "card" }, h("h2", {}, "Payments by head"), hbars(d.payment_heads.map(x => ({ l: x.head, v: x.amount })), { color: C.orange }))),
      h("p", { class: "hint" }, "Your own working books for trustees. Year-end accounts, audit and tax are for your CA."));
  }
  await draw(); return wrap;
}

/* ---------------- planning tools ---------------- */
async function viewBudget(pid) {
  const d = await get("/report/budget" + (pid ? "?project_id=" + pid : "")), t = d.tools;
  if (d.error) return h("div", {}, head("Planning tools"), h("div", { class: "card" }, d.error));
  const sel = h("select", { onchange: async e => { const x = await viewBudget(e.target.value); $("#main").replaceChildren(x); } }, ...d.projects.map(p => h("option", { value: p.id, selected: p.id === d.project_id }, p.name)));
  const P = d.params, LAB = { contingency: "Contingency (0.05 = 5%)", round_up: "Round budget up to", sessions_per_person: "Sessions or visits a person", limit_per_person: "Limit per person (₹)", funds_available: "Funds available to share (₹)", reserve_pct: "Reserve to keep (0.1 = 10%)", share_by: "Share by", central_office_cost: "Central office cost a year (₹)", admin_limit: "Admin limit (0.15 = 15%)", reserve_to_build: "Reserve you want to build (₹)", running_cost_month: "Running cost a month (₹)", months_to_keep: "Months of running cost to keep", camp_people: "Camp: people expected", camp_days: "Camp: days", camp_venue: "Camp: venue a day (₹)", camp_kit_per_person: "Camp: kit per person (₹)", camp_food_per_person_day: "Camp: food per person a day (₹)", camp_other: "Camp: other costs (₹)", camp_sponsor: "Camp: sponsor amount (₹)", corpus_rate: "Corpus interest rate (0.07 = 7%)", cash_opening: "Cash flow opening balance (₹)", salary_increment: "Yearly pay increase (0.08 = 8%)", proposal_overhead: "Overhead the funder allows (0.1 = 10%)" };
  const ins = {}; const grid = h("div", { class: "inputgrid" });
  for (const k in P) { ins[k] = k === "share_by" ? h("select", {}, ...["By budget", "My share %"].map(o => h("option", { selected: P[k] === o }, o))) : h("input", { value: P[k] ?? "" }); grid.append(h("div", {}, h("label", {}, LAB[k] || k), ins[k])); }
  const saveParams = async () => { const o = {}; for (const k in ins) o[k] = ins[k].value; o.tool_project_id = String(d.project_id); if (await must(() => put("/tool-settings", o))) { toast("Saved"); $("#main").replaceChildren(await viewBudget(d.project_id)); } };
  const tool = (n, title, sub, ...kids) => h("div", { class: "card tool" }, h("div", { class: "tag" }, `Tool ${n} / 15`), h("h2", {}, title), sub ? h("div", { class: "hint", style: "margin:-6px 0 8px" }, sub) : null, ...kids);
  const g = t.t01.groups;
  return h("div", { class: "printable" }, head("Planning tools", "15 calculators from your own budget lines, funds and registers. Rates and limits are yours to set."),
    h("div", { class: "bar noprint" }, "Project to plan ", sel, h("span", { class: "grow" }), h("button", { class: "btn pri", onclick: () => showPrint("proposal", t.t15) }, "Print proposal budget")),
    h("details", { class: "card noprint", style: "margin-bottom:14px" }, h("summary", {}, "Your rules and planning figures"), h("div", { style: "margin-top:10px" }, grid, h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: saveParams }, "Save and recalculate")))),
    h("div", { class: "grid2 tools" },
      tool("01", "Project budget builder", `${t.t01.project} · ${t.t01.lines} budget lines`, kvTable([...Object.entries(g).map(([k, v]) => [k, money(v)]), ["Lines total", money(t.t01.lines_total)], [`Contingency ${pct(t.t01.contingency_pct)}`, money(t.t01.contingency)], ["Total project budget", money(t.t01.total)], [`Budget a month (${t.t01.months} months)`, money(t.t01.per_month)]])),
      tool("02", "Cost per beneficiary", `${IN.format(t.t01.people)} people planned`, kvTable([["Cost per person", money(t.t02.cost_per_person)], ["Direct cost per person", money(t.t02.direct_per_person)], ["Per person a month", money(t.t02.per_month)], ["Per session", money(t.t02.per_session)], ["Direct share of budget", pct(t.t02.direct_share)], [`People reached at your limit (${money(t.t02.limit)})`, IN.format(t.t02.reach_at_limit)], ["Against your limit", t.t02.verdict]])),
      tool("03", "Fund allocation by project", `${money(t.t03.available)} available, ${money(t.t03.reserve)} kept in reserve`, mkTable([["project", "Project"], ["budget", "Budget", "money"], ["share", "Share", "money"], ["cover", "Cover", "pct"], ["still", "Still to find", "money"]], t.t03.rows), kvTable([["Shared out", money(t.t03.shared)], ["Left after sharing", money(t.t03.left)], ["Still to find", money(t.t03.still_to_find)]])),
      tool("04", "Restricted vs general funds", "", mkTable([["type", "Type"], ["opening", "Opening", "money"], ["received", "Received", "money"], ["spent", "Spent", "money"], ["balance", "Balance", "money"]], t.t04.types), kvTable([["Free share of all funds", pct(t.t04.free_share)], ["Months covered by general funds", t.t04.months_covered == null ? "–" : t.t04.months_covered.toFixed(1)], [`General funds to keep (${t.t04.months_to_keep} months)`, money(t.t04.keep)], ["Short of that", money(t.t04.short)], ["Funds below zero", t.t04.below_zero]])),
      tool("05", "Admin cost percent", "All project budget lines plus central office", kvTable([["Admin cost", money(t.t05.admin)], ["Total need", money(t.t05.need)], ["Admin share", pct(t.t05.admin_share)], ["Programme share", pct(t.t05.work_share)], ["Fundraising share", pct(t.t05.fundraising_share)], [`Your limit ${pct(t.t05.limit)}`, t.t05.over ? "Over by " + money(-t.t05.room) : "Room left " + money(t.t05.room)]])),
      tool("06", "Donation target & shortfall", "Your own planning figures, not a promise of donations", kvTable([["Total need", money(t.t06.need)], ["Reserve you want to build", money(t.t06.reserve_to_build)], ["Target", money(t.t06.target)], ["Funds promised", money(t.t06.promised)], ["Shortfall", money(t.t06.shortfall)], ["Shortfall a month", money(t.t06.per_month)], ["Average gift so far", money(t.t06.avg_gift)], ["Donors to reach", t.t06.donors_to_reach == null ? "–" : IN.format(t.t06.donors_to_reach)]])),
      tool("07", "Event or camp cost", "Set the camp figures in 'Your rules'", kvTable([["Venue", money(t.t07.venue * t.t07.days)], ["Kits", money(t.t07.kits)], ["Food", money(t.t07.food)], ["Other", money(t.t07.other)], ["Camp cost", money(t.t07.cost)], ["Cost per person", money(t.t07.per_person)], ["Sponsor gap", money(t.t07.sponsor_gap)]])),
      tool("08", "Fundraising cost ratio", "", mkTable([["name", "Appeal"], ["cost", "Cost", "money"], ["raised", "Raised", "money"], ["cost_per_100", "Cost per ₹100", "money"]], t.t08.appeals), kvTable([["Net raised", money(t.t08.net)], ["Cost per ₹100 raised", t.t08.cost_per_100 == null ? "–" : money(t.t08.cost_per_100)], ["Best activity", t.t08.best || "–"]])),
      tool("09", "Salary budget", `${t.t09.staff} staff, ${t.t09.volunteers} volunteers`, kvTable([["Pay a month", money(t.t09.pay_month)], ["Volunteer pay-back a month", money(t.t09.volunteer_payback_month)], ["Cost a year", money(t.t09.cost_year)], [`Next year (+${pct(t.t09.increment)})`, money(t.t09.next_year)], ...Object.entries(t.t09.by_role).map(([k, v]) => ["· " + k, money(v)])])),
      tool("11", "Cash flow by month", `Opening ${money(t.t11.opening)}. Edit months under Planning → Cash flow plan`, mkTable([["month", "Month"], ["inflow", "In", "money"], ["outflow", "Out", "money"], ["closing", "Closing", "money"]], t.t11.months), t.t11.lowest ? h("p", { class: "hint" }, `Lowest month: ${t.t11.lowest.month} at ${money(t.t11.lowest.closing)}`) : null),
      tool("12", "Fund balance after plan", "", kvTable([["All fund balances today", money(t.t12.total)], ["Planned money in", money(t.t12.planned_in)], ["Planned money out", money(t.t12.planned_out)], ["Balance after plan", money(t.t12.after_plan)]])),
      tool("13", "Corpus interest estimate", "An estimate at your rate. Not a promise.", kvTable([["Corpus", money(t.t13.corpus)], [`Interest a year at ${pct(t.t13.rate)}`, money(t.t13.per_year)], ["Interest a month", money(t.t13.per_month)], ["Corpus in 5 years", money(t.t13.in_5_years)]])),
      tool("14", "Budget vs actual", t.t14.project, kvTable([["Budget", money(t.t14.budget)], ["Spent (activity log)", money(t.t14.spent)], ["Balance", money(t.t14.balance)], ["Used", pct(t.t14.used)], ["Time gone", pct(t.t14.time)], ["Reading", t.t14.verdict || "–"]]))),
    tool("10", "Grant utilisation", "Spend a month to finish on time", mkTable([["code", "Grant"], ["funder", "Funder"], ["used", "Used", "pct"], ["time_gone", "Time", "pct"], ["in_hand", "In hand", "money"], ["spend_per_month", "Spend a month", "money"], ["pace", "Pace", "badge"]], t.t10.grants)));
}

/* ---------------- donor impact report ---------------- */
async function viewImpact() {
  const projects = await get("/t/projects");
  if (!projects.length) return h("div", {}, head("Donor impact report"), h("div", { class: "card" }, "Add a project, its results and its money first."));
  const sel = h("select", {}, ...projects.map(p => h("option", { value: p.id }, p.name))), donor = h("input", { placeholder: "Donor name (optional)" }), gift = h("input", { type: "number", min: 0, placeholder: "Gift amount (optional)" });
  const out = h("div", {});
  async function draw() {
    const r = await must(() => get(`/report/impact?project_id=${sel.value}&donor=${encodeURIComponent(donor.value)}&gift=${gift.value || ""}`)); if (!r) return;
    const sheet = h("div", { class: "sheet" }); sheet.innerHTML = impactHTML(r);
    out.replaceChildren(h("div", { class: "printbar" }, h("button", { class: "btn pri", onclick: () => window.print() }, "Print / save as PDF")), sheet);
  }
  [sel, donor, gift].forEach(e => e.addEventListener("change", draw));
  await draw();
  return h("div", { class: "printable" }, head("Donor impact report", "One A4 page for your donor: results against targets, where the money went, and one real story."),
    h("div", { class: "bar noprint" }, sel, donor, gift, h("button", { class: "btn", onclick: draw }, "Refresh")), out);
}
function impactHTML(r) {
  const n = r.numbers, o = r.org, res = n.results.slice(0, 6), more = n.results.length - res.length;
  const bar = x => `<div class="rbar"><i class="band-${x.band}" style="width:${Math.min(100, (x.done || 0) * 100)}%"></i></div>`;
  const COLS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#008300", "#e34948"];
  const total = r.per100.reduce((s, x) => s + x.used, 0);
  return `<div class="org"><b>${esc(o.name)}</b><div>${esc(o.tagline)}</div><div>${esc(o.address)} · ${esc(o.phone)} · ${esc(o.email)}</div></div>
  <h1>PROJECT IMPACT REPORT</h1>
  <div class="row"><div><b>Project:</b> ${esc(r.project.name)}<br><span class="small">${esc(r.project.place)}${r.project.purpose ? " — " + esc(r.project.purpose) : ""}</span></div><div style="text-align:right"><b>Period:</b> ${esc(r.settings.reporting_period || fd(r.asof))}${r.donor ? `<br><b>Prepared for:</b> ${esc(r.donor)}` : ""}${r.gift ? `<br><b>Your gift:</b> ${money(r.gift)}` : ""}</div></div>
  <h3 style="margin-top:12px">What we set out to do, and what happened</h3>
  ${res.length ? res.map(x => `<div style="margin:6px 0"><div class="row" style="margin:0"><span>${esc(x.result)}</span><span><b>${num(x.achieved)}</b> of ${num(x.target)} ${esc(x.unit || "")} · ${pct(x.done)}</span></div>${bar(x)}</div>`).join("") : `<p class="small">No results typed yet.</p>`}
  ${more > 0 ? `<p class="small">+ ${more} more results kept on file (the report shows the first 6).</p>` : ""}
  <div class="small" style="margin-top:4px">Bars: green ${esc(r.settings.green_from)}%+, light green ${esc(r.settings.light_from)}%+, yellow ${esc(r.settings.yellow_from)}%+, red below.</div>
  <div class="row" style="margin-top:14px;gap:12px"><div style="flex:1;border:1px solid #cfcfcf;padding:8px;border-radius:6px"><div class="small">People reached</div><div class="amt">${IN.format(n.people)}</div></div>
  <div style="flex:1;border:1px solid #cfcfcf;padding:8px;border-radius:6px"><div class="small">Money used</div><div class="amt">${money(n.used)}</div><div class="small">of ${money(n.budget)} budget (${pct(n.money)})</div></div>
  <div style="flex:1;border:1px solid #cfcfcf;padding:8px;border-radius:6px"><div class="small">Balance</div><div class="amt">${money(n.balance)}</div></div></div>
  <h3 style="margin-top:14px">Where every ₹100 went</h3>
  ${total ? `<div class="stack">${r.per100.map((x, i) => `<i style="width:${x.share}%;background:${COLS[i % 8]}" title="${esc(x.head)}"></i>`).join("")}</div>
  <table style="margin-top:6px"><tbody>${r.per100.map((x, i) => `<tr><td style="width:18px"><span style="display:inline-block;width:12px;height:12px;background:${COLS[i % 8]};border-radius:2px"></span></td><td>${esc(x.head)}</td><td style="text-align:right">₹${x.share.toFixed(0)} of every ₹100</td>${r.split ? `<td style="text-align:right">≈ ${money(r.split[i].amount)} of your gift</td>` : ""}</tr>`).join("")}</tbody></table>` : `<p class="small">No money typed yet.</p>`}
  ${r.story ? `<h3 style="margin-top:14px">One story: ${esc(r.story.person)}</h3>
  <table><tbody><tr><td style="width:90px"><b>Before</b></td><td>${esc(r.story.before)}</td></tr><tr><td><b>What we did</b></td><td>${esc(r.story.did)}</td></tr><tr><td><b>After</b></td><td>${esc(r.story.after)}</td></tr></tbody></table>
  ${r.story.quote ? `<p style="font-style:italic;margin:8px 0">“${esc(r.story.quote)}” — ${esc(r.story.person)}</p>` : ""}
  ${r.story.number ? `<p><b style="font-size:18px">${esc(r.story.number)}</b> ${esc(r.story.number_meaning)}</p>` : ""}
  ${r.story_too_long ? `<p class="small" style="color:#c23b3a">Story is long. Shorten it so the report fits one page.</p>` : ""}
  ${r.story.next ? `<p><b>What we will do next:</b> ${esc(r.story.next)}</p>` : ""}` : ""}
  <p class="small" style="margin-top:12px">Prepared by ${esc(r.settings.prepared_by)}${r.settings.designation ? ", " + esc(r.settings.designation) : ""} · ${fd(r.asof)}. Figures are from our own records. Ask the person before using their story.</p>`;
}
async function viewAllProjects() {
  const d = await get("/report/all_projects"), t = d.totals;
  const flagCls = f => f === "On track" ? "green" : f === "No results yet" ? "grey" : "amber";
  return h("div", { class: "printable" }, head("All projects", `For trustees and committee · as on ${fd(d.asof)}`, h("button", { class: "btn sm", onclick: () => window.print() }, "Print")),
    h("div", { class: "cards" }, kpi("Projects", t.projects), kpi("People reached", IN.format(t.people)), kpi("Money used", money(t.used)), kpi("Results achieved", pct(t.work), "average of projects"), kpi("Need a look", t.need_look, "", t.need_look ? "warn" : "")),
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Project", "Stage", "People", "Work done", "Money used", "Time gone", "Flag"].map(x => h("th", { style: "cursor:default" }, x)))),
      h("tbody", {}, ...d.projects.map(p => h("tr", {}, h("td", {}, h("b", {}, p.name), h("div", { class: "hint" }, p.place || "")), h("td", {}, cell(p.stage, "badge")[0]), h("td", { class: "n" }, IN.format(p.people)),
        h("td", { style: "min-width:140px" }, pct(p.work), progress(p.work, p.band === "red" ? C.red : p.band === "yellow" ? C.yellow : C.green)), h("td", { style: "min-width:140px" }, pct(p.money), progress(p.money, C.blue)), h("td", { style: "min-width:120px" }, pct(p.time), progress(p.time, "#8a877f")),
        h("td", {}, h("span", { class: "badge b-" + flagCls(p.flag) }, p.flag))))))),
    h("p", { class: "hint" }, `Flags: money ahead of work by ${d.settings.money_ahead}+ points; time ahead of work by ${d.settings.time_ahead}+ points. Change these under Settings.`));
}
async function viewFormats() {
  const records = await get("/t/records");
  const fsel = h("select", {}, ...META.formats.map(f => h("option", { value: f.name }, f.name))), rsel = h("select", {}, ...records.map(r => h("option", { value: r.id }, `${r.record_no} · ${r.party || ""} · ${fd(r.date)}`)));
  const rows = META.formats.map(f => h("tr", {}, h("td", {}, f.name), h("td", {}, f.title), h("td", {}, f.line1), USER.role === "admin" ? h("td", {}, h("button", { class: "btn sm", onclick: () => editFormat(f) }, "Edit wording")) : null));
  return h("div", {}, head("Print a format", "Pick a format and a record: one A4 page with your header."), h("div", { class: "card", style: "margin-bottom:14px" }, h("div", { class: "bar" }, fsel, rsel, h("button", { class: "btn pri", onclick: () => rsel.value ? showPrint("record", rsel.value, fsel.value) : toast("Add a record first (Documents → Records)", true) }, "Preview & print")), h("div", { class: "hint" }, "Receipts, vouchers, statements and utilisation certificates are printed from their own registers (Donations, Cash book, Donors, Grants).")),
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Format", "Printed title", "Line 1", USER.role === "admin" ? "" : null].filter(x => x !== null).map(x => h("th", { style: "cursor:default" }, x)))), h("tbody", {}, ...rows))));
}
function editFormat(f) {
  const keys = [["title", "Printed title"], ["line1", "Line 1"], ["line2", "Line 2"], ["line3", "Line 3"], ["sign_left", "Sign left"], ["sign_right", "Sign right"]], ins = {};
  const form = h("div", { class: "form" }, ...keys.map(([k, l]) => { ins[k] = h("input", { value: f[k] ?? "" }); return h("div", { class: ["line1", "line2", "line3"].includes(k) ? "full" : "" }, h("label", {}, l), ins[k]); }));
  ins.show_lines = h("select", {}, ...["Y", "N"].map(o => h("option", { selected: f.show_lines === o }, o))); ins.show_amounts = h("select", {}, ...["Y", "N"].map(o => h("option", { selected: f.show_amounts === o }, o)));
  form.append(h("div", {}, h("label", {}, "Print the lines table (Y/N)"), ins.show_lines), h("div", {}, h("label", {}, "Print amounts (Y/N)"), ins.show_amounts));
  const close = modal("Edit · " + f.name, h("div", {}, form, h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"), h("button", { class: "btn pri", onclick: async () => { const o = { name: f.name }; for (const k in ins) o[k] = ins[k].value; if (await must(() => put("/formats", o))) { close(); META = await get("/meta"); toast("Saved"); route(); } } }, "Save"))), { wide: true });
}

/* ---------------- birthdays ---------------- */
async function viewBirthdays(days = 30) {
  const [d, log] = await Promise.all([get("/birthdays?days=" + days), ["admin", "accountant"].includes(USER.role) ? get("/email-log") : []]);
  const canSend = ["admin", "accountant"].includes(USER.role);
  const MON_D = s => { const [, m, dd] = s.split("-"); return `${+dd} ${MON[+m - 1]}`; };
  const today = d.people.filter(p => p.days_away === 0);
  const status = p => p.sent ? h("span", { class: "badge b-green" }, "Wish sent") : p.wishes === "N" ? h("span", { class: "badge b-grey" }, "Opted out") : !p.email ? h("span", { class: "badge b-amber" }, "No email") : h("span", { class: "badge b-blue" }, p.days_away === 0 ? "Due today" : "Scheduled");
  const sendOne = async p => { const r = await must(() => post("/birthdays/send", { tbl: p.tbl, id: p.id })); if (r) { toast(r.status === "sent" ? `Wish sent to ${p.name}` : r.reason, r.status !== "sent"); $("#main").replaceChildren(await viewBirthdays(days)); } };
  const runAll = async () => { const r = await must(() => post("/birthdays/run", {})); if (r) { toast(`Sent ${r.sent}, skipped ${r.skipped}, failed ${r.failed}` + (r.details.length ? ": " + r.details.slice(0, 2).join("; ") : ""), r.failed > 0); $("#main").replaceChildren(await viewBirthdays(days)); } };
  const sel = h("select", { onchange: async e => $("#main").replaceChildren(await viewBirthdays(+e.target.value)) }, ...[[7, "Next 7 days"], [30, "Next 30 days"], [60, "Next 60 days"], [90, "Next 90 days"], [366, "Whole year"]].map(([v, l]) => h("option", { value: v, selected: v === days }, l)));
  const t = h("div", { class: "tablewrap" }, d.people.length ? h("table", {}, h("thead", {}, h("tr", {}, ...["Name", "Who", "Birthday", "Turning", "When", "Email", "Status", ""].map(x => h("th", { style: "cursor:default" }, x)))),
    h("tbody", {}, ...d.people.map(p => h("tr", { style: p.days_away === 0 ? "background:#fff8e6" : "" }, h("td", {}, h("b", {}, p.name)), h("td", {}, p.kind), h("td", {}, MON_D(p.birthday)), h("td", { class: "n" }, p.turning ?? "–"),
      h("td", {}, p.days_away === 0 ? "Today 🎂" : p.days_away === 1 ? "Tomorrow" : `in ${p.days_away} days (${MON_D(p.next_date)})`), h("td", {}, p.email || "–"), h("td", {}, status(p)),
      h("td", {}, canSend && !p.sent && p.wishes !== "N" && p.email ? h("button", { class: "btn sm", onclick: () => sendOne(p) }, p.days_away === 0 ? "Send wish now" : "Send early") : null))))) : h("div", { class: "empty" }, "No birthdays in this period. Add a birthday on a donor or team member to see them here."));
  const setup = !d.email_ready ? h("div", { class: "card", style: "margin-bottom:14px;border-color:#e0a100" }, "Email is not set up yet, so wishes cannot be sent. ", USER.role === "admin" ? h("a", { href: "#/a/settings" }, "Set up email in Settings →") : "Ask an administrator to set up email in Settings.") : null;
  return h("div", { class: "printable" }, head("Birthdays", "Donors and team members with a birthday coming up. Wishes go by email, once a year per person."),
    setup, h("div", { class: "cards" }, kpi("Today", today.length, today.map(p => p.name).join(", ") || "none", today.length ? "warn" : ""), kpi("In this period", d.people.length), kpi("Wishes sent this year", d.sent_this_year), kpi("Automatic sending", d.auto ? "On" : "Off", d.auto ? "runs daily after the set hour" : "switch on in Settings")),
    h("div", { class: "bar noprint" }, sel, h("span", { class: "grow" }), canSend && today.length ? h("button", { class: "btn pri", onclick: runAll }, `Send today's wishes (${today.length})`) : null),
    t, canSend ? h("div", { style: "margin-top:16px" }, h("h2", {}, "Recent emails"), log.length ? mkTable([["ts", "When"], ["kind", "Kind"], ["to_addr", "To"], ["subject", "Subject"], ["status", "Result", "badge"], ["error", "Note"]], log.slice(0, 20).map(r => ({ ...r, ts: r.ts.replace("T", " ") }))) : h("div", { class: "hint" }, "Nothing sent yet.")) : null,
    h("p", { class: "hint" }, "Only people with an email address and “Send birthday wishes” = Yes get a wish. Untick it on a donor who asked not to be contacted. Use only addresses people gave you for this purpose."));
}
