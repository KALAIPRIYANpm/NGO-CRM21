// v13: Yearly plan. Calendar items, company next steps, decisions and compliance dates in one 12-month list.
async function viewYearPlan() {
  const d = await get("/yearplan");
  const months = {};
  d.items.forEach(i => { const k = i.date.slice(0, 7); (months[k] = months[k] || []).push(i); });
  const mname = k => new Date(k + "-01T00:00:00").toLocaleString("en-IN", { month: "long", year: "numeric" });
  const tone = { Calendar: "#0f5e63", Company: "#8a5a00", Decision: "#8a1f11", Compliance: "#4a4a4a" };
  const row = i => h("div", { style: "display:flex;gap:10px;align-items:baseline;padding:6px 0;border-top:1px solid var(--line,#e3e8ea)" },
    h("div", { style: "width:92px;flex:none;font-variant-numeric:tabular-nums" }, new Date(i.date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })),
    h("div", { style: "width:86px;flex:none;font-weight:600;color:" + (tone[i.type] || "inherit") }, i.type),
    h("div", { style: "flex:1;min-width:200px" }, h("a", { href: i.link }, i.title), i.detail ? h("div", { class: "hint" }, i.detail) : null),
    i.prep ? h("span", { class: "newpill" }, "Prepare now") : null);
  const keys = Object.keys(months).sort();
  const stages = ["Target", "Approached", "Pitched", "Due diligence", "Plan approval", "Sanctioned", "Disbursing", "Reporting", "Renewal"];
  const by = Object.fromEntries(d.pipeline.map(p => [p.stage, p]));
  return h("div", {}, head("Yearly plan", "The next 12 months: festivals and giving windows, company next steps and decisions, and compliance dates."),
    h("div", { class: "card noprint", style: "margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center" },
      h("a", { class: "btn", href: "#/t/plan_calendar" }, "Edit the calendar"), h("a", { class: "btn", href: "#/t/csr_pipeline" }, "Company pipeline")),
    h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "Company funding by stage"),
      h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, ...stages.map(s => h("div", { style: "flex:1;min-width:110px;padding:8px;border:1px solid var(--line,#d8dee0);border-radius:8px" },
        h("div", { class: "hint" }, s), h("b", {}, String((by[s] || {}).n || 0)), (by[s] && (by[s].ask || by[s].sanctioned)) ? h("div", { class: "hint" }, "₹" + Math.round(s === "Sanctioned" || s === "Disbursing" || s === "Reporting" ? by[s].sanctioned : by[s].ask).toLocaleString("en-IN")) : null)))),
    keys.length ? h("div", {}, ...keys.map(k => h("div", { class: "card", style: "margin-bottom:10px" }, h("h2", {}, mname(k)), ...months[k].map(row)))) : h("div", { class: "empty" }, "Nothing planned yet. Press Add the standard calendar, then add the companies you are talking to."));
}
