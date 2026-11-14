/* v9 screens: company partners, cash forecast, key relationships, board pack. */
"use strict";
Object.assign(CST, { Prospect: "grey", Pitched: "blue", Proposal: "blue", Approved: "green", Active: "green", "Renewal due": "amber", Lapsed: "red", OK: "green", "Below reserve": "amber", Short: "red", Overdue: "red", Expected: "blue", Received: "green" });
const pNoAccess = t => h("div", {}, head(t), h("div", { class: "card" }, "Not available for your role."));
const flagPills = fl => fl.length ? h("div", { style: "display:flex;flex-wrap:wrap;gap:4px;max-width:210px" }, ...fl.map(f => h("span", { class: "badge b-" + (/overdue|passed|No owner|No contact|same/i.test(f) ? "red" : "amber") }, f))) : h("span", { class: "hint" }, "Nothing flagged");
const bar = (v, max, color) => h("div", { style: "background:#eee;border-radius:4px;height:10px;min-width:80px" }, h("div", { style: `width:${Math.max(2, Math.min(100, max ? v / max * 100 : 0))}%;background:${color || "var(--brand)"};height:10px;border-radius:4px` }));

/* ---------------- company partners ---------------- */
async function viewPartners() {
  if (!FIN_ROLES.includes(USER.role)) return pNoAccess("Company partners");
  const d = await get("/partners/pipeline"), s = d.summary;
  const portal = async (r, revoke) => {
    const x = await must(() => post(`/partners/${r.id}/portal`, { revoke }));
    if (!x) return;
    if (revoke) { toast("Company page switched off"); return route(); }
    const url = location.origin + x.path;
    modal("Private page for " + r.name, h("div", {}, h("p", {}, "Send this link to your contact at the company. They see only their own gifts, events and hours. Anyone with the link can open it, so share it only with them."),
      h("input", { value: url, readonly: true, onfocus: e => e.target.select(), style: "width:100%" }),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => copyText(url) }, "Copy link"), h("a", { class: "btn pri", href: url, target: "_blank", rel: "noopener" }, "Open it"))));
    route();
  };
  const rows = d.items.map(r => h("tr", {}, h("td", {}, h("a", { href: "javascript:void 0", onclick: () => openForm("partners", r, null, () => route()) }, r.name), h("div", { class: "hint" }, [r.code, r.contact_name].filter(Boolean).join(" · ")),
      h("div", { style: "margin-top:4px" }, h("button", { class: "btn sm", onclick: () => portal(r, false) }, r.portal_token ? "Company page" : "Make company page"), r.portal_token ? [" ", h("button", { class: "btn sm", onclick: () => portal(r, true) }, "Switch off")] : null)),
    h("td", {}, pill(r.stage)), h("td", { class: "n" }, r.expected_amount ? money(r.expected_amount) : ""),
    h("td", { class: "n" }, r.given ? money(r.given) : "", r.gifts ? h("div", { class: "hint" }, r.gifts + " gift" + (r.gifts === 1 ? "" : "s")) : null),
    h("td", { class: "n" }, r.events ? r.events + " · " + (+r.hours.toFixed(1)) + " h" : ""),
    h("td", {}, r.next_step || "", r.next_step_date ? h("div", { class: "hint" }, fd(r.next_step_date)) : null, r.owner ? h("div", { class: "hint" }, "Owner: " + r.owner + (r.backup_owner ? " · backup " + r.backup_owner : "")) : null),
    h("td", { style: "min-width:150px" }, flagPills(r.flags))));
  return h("div", {}, head("Company partners", "Companies you work with or hope to. Move each one along the stages, and record what it gives and does with you."),
    careTiles(careTile(s.total, "companies"), careTile(s.live, "approved or active"), careTile(money(s.expected_live), "expected this year"), careTile(money(s.given), "given so far"), careTile(s.events + " · " + (+s.hours.toFixed(1)) + " h", "events · volunteer hours"), careTile(s.attention, "need attention")),
    h("div", { class: "card", style: "margin-bottom:10px" }, h("div", { class: "hint", style: "margin-bottom:6px" }, "Pipeline"),
      h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, ...d.stages.map(x => h("div", { style: "flex:1;min-width:110px;border:1px solid var(--line,#ddd);border-radius:8px;padding:8px" }, pill(x.stage), h("div", { style: "font-size:20px;font-weight:700" }, x.count), h("div", { class: "hint" }, x.expected ? money(x.expected) : "—"))))),
    h("div", { class: "actions noprint", style: "margin-bottom:10px" }, h("button", { class: "btn pri", onclick: () => openForm("partners", null, { stage: "Prospect" }, () => route()) }, "Add a company"),
      h("button", { class: "btn", onclick: () => openForm("partner_events", null, { status: "Planned" }, () => route()) }, "Add an event"), h("a", { class: "btn", href: "#/t/partner_events" }, "All events"), h("a", { class: "btn", href: "#/t/partners" }, "See as a list")),
    careTable([["Company"], ["Stage"], ["Expected", "n"], ["Given", "n"], ["Events", "n"], ["Next step and owner"], ["Flags"]], rows, "No companies yet. Press Add a company."),
    h("p", { class: "hint" }, "To record a gift that came through a company, open the donation and choose the company. Flags appear when a renewal is near or has passed, a next step is overdue, nobody has been in touch for 60 days, or no owner or backup is named."));
}

/* ---------------- cash forecast ---------------- */
async function viewForecast() {
  if (!FIN_ROLES.includes(USER.role)) return pNoAccess("Cash forecast");
  const f = await get("/forecast"), fs = f.funders;
  const max = Math.max(1, ...f.rows.map(r => Math.abs(r.free)));
  const cost = h("input", { type: "number", min: 0, value: (META.settings.core_monthly_cost || 0), style: "width:140px" }), res = h("input", { type: "number", min: 0, step: "0.5", value: (META.settings.reserve_months || 3), style: "width:80px" });
  const rows = f.rows.map(r => h("tr", {}, h("td", {}, r.label), h("td", { class: "n" }, money(r.promises)), h("td", { class: "n" }, money(r.funders)), h("td", { class: "n" }, r.planned_in ? money(r.planned_in) : ""),
    h("td", { class: "n" }, money(r.outflow)), h("td", { class: "n", style: r.free < 0 ? "color:#b00020;font-weight:600" : "" }, money(r.free)), h("td", {}, bar(Math.max(0, r.free), max, r.status === "OK" ? "#2e7d32" : r.status === "Short" ? "#b00020" : "#e08a00")), h("td", {}, pill(r.status))));
  const lo = f.lowest;
  return h("div", {}, head("Cash forecast", "Twelve months ahead, from the money you have entered. It shows early when free cash could run short."),
    careTiles(careTile(money(f.opening), "cash in all funds today"), careTile(money(f.restricted), "of which restricted"), careTile(money(f.free), "free cash"), careTile(money(f.monthly_cost), "monthly cost used"), careTile(f.runway_months == null ? "—" : f.runway_months + " mo", "free cash covers"), careTile(lo ? lo.label : "—", lo ? "lowest point: " + money(lo.free) : "lowest month")),
    fs.overdue ? h("div", { class: "card", style: "border-left:4px solid #b00020;margin-bottom:10px" }, h("b", {}, fs.overdue + " funder payment" + (fs.overdue === 1 ? " is" : "s are") + " overdue, " + money(fs.overdue_amount) + " in all. "), h("a", { href: "#/t/tranches" }, "See expected funder payments")) : null,
    careTable([["Month"], ["Giving promises", "n"], ["Funder payments", "n"], ["Your plan lines", "n"], ["Money out", "n"], ["Free cash", "n"], [""], ["Status"]], rows, "No months."),
    h("div", { class: "card noprint", style: "margin-top:10px" }, h("div", { class: "hint", style: "margin-bottom:6px" }, "Planning inputs"),
      h("div", { class: "bar" }, h("label", {}, "Core monthly cost (₹, 0 = use average of last 3 months) ", cost), h("label", {}, "Reserve target (months) ", res),
        h("button", { class: "btn pri", onclick: async () => { if (await must(() => put("/tool-settings", { core_monthly_cost: cost.value || "0", reserve_months: res.value || "3" }))) { META.settings.core_monthly_cost = cost.value || "0"; META.settings.reserve_months = res.value || "3"; toast("Saved"); route(); } } }, "Save"),
        h("a", { class: "btn", href: "#/t/tranches" }, "Funder payments"), h("a", { class: "btn", href: "#/t/cashflow_plan" }, "Cash flow plan lines"))),
    h("ul", { class: "hint" }, ...f.notes.map(n => h("li", {}, n)), h("li", {}, `Status is Below reserve when free cash is under ${money(f.reserve)} (${f.reserve_months} months of cost), and Short when it is below zero.`)));
}

/* ---------------- key relationships ---------------- */
async function viewRelations() {
  if (!FIN_ROLES.includes(USER.role)) return pNoAccess("Key relationships");
  const d = await get("/relations"), s = d.summary;
  const mx = Math.max(1, ...d.owners.map(o => o.value));
  const rows = d.items.map(r => h("tr", {}, h("td", {}, h("a", { href: r.link }, r.name), h("div", { class: "hint" }, r.code || "")), h("td", {}, r.kind), h("td", { class: "n" }, money(r.value)),
    h("td", {}, r.owner || h("span", { class: "hint" }, "—")), h("td", {}, r.backup || h("span", { class: "hint" }, "—")), h("td", {}, fd(r.last)), h("td", {}, flagPills(r.risk))));
  return h("div", {}, head("Key relationships", "Who knows your major donors, companies and funders, and who covers if they leave."),
    careTiles(careTile(s.total, "key relationships"), careTile(s.at_risk, "without owner or backup"), careTile(money(s.value_at_risk), "value at risk"), careTile(s.top_owner || "—", s.top_owner ? Math.round(s.top_share * 100) + "% of value" : "largest holder")),
    d.owners.length ? h("div", { class: "card", style: "margin-bottom:10px" }, h("div", { class: "hint", style: "margin-bottom:6px" }, "Value held by each person"),
      ...d.owners.map(o => h("div", { style: "display:flex;gap:10px;align-items:center;margin:4px 0" }, h("div", { style: "width:150px" }, o.owner), h("div", { style: "flex:1" }, bar(o.value, mx, o.owner === "(no owner)" ? "#b00020" : null)), h("div", { style: "width:130px;text-align:right" }, money(o.value) + " · " + Math.round(o.share * 100) + "%")))) : null,
    careTable([["Name"], ["Kind"], ["Value", "n"], ["Owner"], ["Backup"], ["Last gift or contact"], ["Flags"]], rows, "Nothing here yet. Donors who have given " + money(d.major_min) + " or more, companies in talks, and all funders appear here."),
    h("p", { class: "hint" }, `Major donors are those who have given ${money(d.major_min)} or more in all (change it in Settings → Money planning). Set Relationship owner, Backup person and Handover note on the donor, company or grant. Value for a company is its expected support; for a funder it is the sanctioned amount.`));
}

/* ---------------- board pack ---------------- */
async function viewBoard() {
  if (!FIN_ROLES.includes(USER.role)) return pNoAccess("Board pack");
  const b = await get("/board"), f = b.forecast;
  const notes = h("textarea", { rows: 3, placeholder: "Optional note to print at the end (for example, the chairperson's remarks)", style: "width:100%" });
  const open = () => window.open("/api/boardpack?notes=" + encodeURIComponent(notes.value), "_blank");
  const dec = b.decisions.map(d => h("tr", {}, h("td", {}, fd(d.date)), h("td", {}, d.decision), h("td", {}, d.owner), h("td", {}, d.due ? fd(d.due) : "", d.overdue ? [" ", pill("Overdue")] : null)));
  return h("div", {}, head("Board pack", "One page for the trustees, built from your own records. Check it, add a note and print it."),
    careTiles(careTile(money(b.income), "income this financial year"), careTile(money(b.spend), "spent"), careTile(money(b.surplus), "surplus or shortfall"), careTile(money(f.free), "free cash"), careTile(b.partners.summary.live, "live company partners"), careTile(b.decisions.length, "open decisions")),
    h("div", { class: "card", style: "margin-bottom:10px" }, h("div", { class: "hint", style: "margin-bottom:6px" }, "What the board should look at first"),
      b.risks.length ? h("ul", {}, ...b.risks.map(r => h("li", {}, r))) : h("div", {}, "Nothing is flagged by the records.")),
    h("div", { class: "card noprint", style: "margin-bottom:10px" }, notes, h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: open }, "Open board pack to print"), h("a", { class: "btn", href: "#/r/forecast" }, "Cash forecast"), h("a", { class: "btn", href: "#/r/relations" }, "Key relationships"))),
    h("div", { class: "actions noprint", style: "margin-bottom:6px" }, h("button", { class: "btn", onclick: () => openForm("decisions", null, { date: b.asof, status: "Open" }, () => route()) }, "Add a decision"), h("a", { class: "btn", href: "#/t/decisions" }, "All decisions")),
    careTable([["Meeting date"], ["Open decision or action"], ["Owner"], ["Due"]], dec, "No open decisions."));
}
