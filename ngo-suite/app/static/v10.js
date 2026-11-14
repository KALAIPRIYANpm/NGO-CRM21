/* v10 screens: yearly compliance check, risk map, help and page guide, donor page, event people, display settings. */
"use strict";
Object.assign(CST, { fix: "red", warn: "amber", ok: "green", High: "red", Medium: "amber", Low: "green", Watching: "blue", Closed: "green", "Review overdue": "red",
  Interested: "grey", "Talked to family": "blue", "Will being drafted": "blue", "Confirmed in writing": "green", Received: "green", Declined: "grey" });

/* ---------------- display: dark mode and accent colour ---------------- */
function displayDialog() {
  const theme = h("select", {}, ...[["auto", "Same as my device"], ["light", "Light"], ["dark", "Dark"]].map(([v, l]) => h("option", { value: v, selected: window.themeChoice() === v }, l)));
  const accent = h("input", { type: "color", value: window.accentChoice() || (BRAND && BRAND.color) || "#0f5e63", style: "width:60px;height:36px;padding:2px" });
  let touched = false; accent.addEventListener("input", () => { touched = true; });
  const close = modal("Display", h("div", {}, h("p", { class: "hint" }, "These choices are kept only in this browser. Your organisation's brand colour is unchanged for other people."),
    h("label", {}, "Light or dark"), theme, h("label", { style: "margin-top:10px;display:block" }, "Accent colour"), accent,
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => { window.setThemeChoice("auto", ""); close(); toast("Display reset"); } }, "Reset"), h("button", { class: "btn", onclick: () => close() }, "Cancel"),
      h("button", { class: "btn pri", onclick: () => { window.setThemeChoice(theme.value, touched ? accent.value : undefined); close(); } }, "Save"))));
}

/* ---------------- donor page ("Your giving") ---------------- */
async function donorPageDialog(r) {
  const x = await must(() => post(`/donors/${r.id}/portal`, {})); if (!x) return;
  const url = location.origin + x.path;
  const close = modal("Giving page for " + r.name, h("div", {}, h("p", {}, "Send this link to the donor. They see only their own gifts, what the work achieved, and any regular gift. Anyone with the link can open it, so share it only with them."),
    h("input", { value: url, readonly: true, onfocus: e => e.target.select(), style: "width:100%" }),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: async () => { if (await must(() => post(`/donors/${r.id}/portal`, { revoke: true }))) { close(); toast("Giving page switched off"); } } }, "Switch it off"),
      h("button", { class: "btn", onclick: () => copyText(url) }, "Copy link"), h("a", { class: "btn pri", href: url, target: "_blank", rel: "noopener" }, "Open it"))));
}

/* ---------------- people at an office event ---------------- */
async function eventPeopleDialog(ev) {
  const box = h("div", {});
  let close;
  const draw = async () => {
    const rows = await must(() => get("/t/event_people?f_event_id=" + ev.id)) || [];
    const name = h("input", { placeholder: "Name", style: "flex:1 1 150px;width:auto" }), hours = h("input", { type: "number", step: "0.5", min: "0", placeholder: "Hours", style: "flex:0 0 90px;width:90px" }), role = h("input", { placeholder: "What they did (optional)", style: "flex:1 1 170px;width:auto" });
    const add = async () => { if (!name.value.trim()) return toast("Enter a name", true); if (await must(() => post("/t/event_people", { event_id: ev.id, name: name.value.trim(), hours: hours.value || 0, role: role.value }))) { await draw(); window._refreshRegister && window._refreshRegister(); } };
    box.replaceChildren(h("p", { class: "hint" }, `${rows.length} ${rows.length === 1 ? "person" : "people"} listed, ${rows.reduce((s, r) => s + (+r.hours || 0), 0)} hours. The "came" count and hours on the event are set from this list.`),
      rows.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", { class: "n" }, "Hours"), h("th", {}, "Role"), h("th", {}))),
        h("tbody", {}, ...rows.map(r => h("tr", {}, h("td", {}, r.name), h("td", { class: "n" }, r.hours || 0), h("td", {}, r.role || ""),
          h("td", {}, h("button", { class: "btn sm", onclick: async () => { if (await must(() => del("/t/event_people/" + r.id))) { await draw(); window._refreshRegister && window._refreshRegister(); } } }, "Remove"))))))) : h("div", { class: "empty" }, "Nobody listed yet."),
      h("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-top:10px" }, name, hours, role, h("button", { class: "btn pri", onclick: add }, "Add")),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Done")));
  };
  await draw(); close = modal("People at: " + ev.title, box, { wide: true });
}

/* ---------------- yearly compliance check ---------------- */
async function viewYearCheck() {
  if (!FIN_ROLES.includes(USER.role)) return h("div", {}, head("Yearly compliance check"), h("div", { class: "card" }, "Not available for your role."));
  const d = await get("/yearcheck"), s = d.summary;
  const label = { ok: "Fine", warn: "Look at this", fix: "Needs action" };
  const areas = [...new Set(d.items.map(i => i.area))];
  return h("div", {}, head("Yearly compliance check", "A checklist built from what you have entered. It does not replace your CA: use it to see what to ask about."),
    careTiles(careTile(s.fix, "Need action"), careTile(s.warn, "Look at these"), careTile(s.ok, "Fine")),
    h("div", { class: "card noprint", style: "margin-bottom:12px" }, h("button", { class: "btn", onclick: async () => { const r = await must(() => post("/yearcheck/starter", {})); if (r) { toast(r.added ? `${r.added} item(s) added with placeholder dates. Set the real dates.` : "Nothing to add; the usual items are already there"); route(); } } }, "Add the standard items to my calendar"),
      h("span", { class: "hint", style: "margin-left:8px" }, "Adds only what is missing, with placeholder dates you must correct with your CA.")),
    ...areas.map(a => h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, a),
      careTable([["Check"], ["Result"], ["Detail"]], d.items.filter(i => i.area === a).map(i =>
        h("tr", {}, h("td", {}, i.link ? h("a", { href: i.link }, i.title) : i.title), h("td", {}, pill(label[i.status], i.status === "ok" ? "green" : i.status === "warn" ? "amber" : "red")), h("td", {}, i.detail)))))));
}

/* ---------------- risk map ---------------- */
async function viewRiskMap() {
  if (!FIN_ROLES.includes(USER.role)) return h("div", {}, head("Risk map"), h("div", { class: "card" }, "Not available for your role."));
  const rows = (await get("/t/risks")).filter(r => r.status !== "Closed");
  const cell = (l, i) => {
    const here = rows.filter(r => +r.likelihood === l && +r.impact === i), sc = l * i, col = sc >= 15 ? "#f3c9c8" : sc >= 8 ? "#fbe6bd" : "#d6efdd";
    const short = t => { const x = t.replace(" (sample)", ""); return x.length > 32 ? x.slice(0, 31) + "…" : x; };
    return h("td", { style: `background:${col};color:#14202b;vertical-align:top;height:64px;padding:4px 6px;border:1px solid #fff` }, ...here.map(r => h("div", { style: "font-size:12px;margin-bottom:2px" }, "• " + short(r.title))));
  };
  const grid = h("table", { style: "border-collapse:collapse;table-layout:fixed;width:100%" }, h("tbody", {}, ...[5, 4, 3, 2, 1].map(l => h("tr", {}, h("th", { style: "padding:4px 8px;text-align:right;font-weight:600;width:36px" }, l), ...[1, 2, 3, 4, 5].map(i => cell(l, i)))),
    h("tr", {}, h("th", {}), ...[1, 2, 3, 4, 5].map(i => h("th", { style: "text-align:center;font-weight:600;padding:4px" }, i)))));
  return h("div", {}, head("Risk map", "Open risks placed by how likely (up) and how bad (across). Red needs a plan and an owner."),
    h("div", { class: "card" }, h("div", { class: "hint", style: "margin-bottom:6px" }, "Up: how likely (1 rare to 5 almost sure). Across: how bad (1 small to 5 severe)."), h("div", { class: "tablewrap" }, grid),
      h("div", { class: "actions" }, h("a", { class: "btn pri", href: "#/t/risks" }, "Open the risk register"))));
}

/* ---------------- help and page guide ---------------- */
const HELP = {
  "#/t/official_docs": "Library of registration, tax, CSR and audit papers with scans, numbers and expiry dates.",
  "#/r/proposal": "Builds a draft CSR proposal from your records, to print or save as PDF.",
  "#/dashboard": "Your daily starting point: money raised, work done, and what needs attention today.", "#/r/weekly": "Last week in one page, with overdue payments, decisions and renewals. Share it with trustees.",
  "#/r/automation": "Switch on routine jobs such as birthday wishes, thank-you notes and reminders.", "#/r/field": "A phone-friendly page for staff to log activities, mark attendance and claim expenses, even offline.",
  "#/r/followups": "Everyone you promised to call or write to, sorted by date.", "#/r/inbox": "Replies from WhatsApp and SMS arrive here. A reply of STOP removes the person from future messages.",
  "#/r/messages": "Send one message to many people by WhatsApp, SMS or email. Four steps: how, who, what, when.", "#/t/contacts": "People who are not donors: volunteers, officials, media and well-wishers.",
  "#/t/interactions": "A diary of calls, visits and messages with each donor.", "#/t/templates": "Ready-made messages you can reuse and edit.", "#/r/birthdays": "Donors and contacts with birthdays coming up, so you can send wishes.",
  "#/t/donors": "Every donor with phone, city, owner and backup owner. Use Giving page to share a private page with a donor.", "#/t/donations": "Record each gift once. Receipts and thank-you notes follow from here.",
  "#/t/pledges": "Promises made on your public Donate page, waiting for you to follow up.", "#/r/promises": "Monthly and yearly donors, showing who has paid and who is late.",
  "#/r/lapse": "Regular givers who have gone quiet, so you can reach out in time.", "#/r/donors": "Who gives most, how often, and from where.", "#/r/dups": "Spot the same donor entered twice, and merge them.",
  "#/r/partners": "The pipeline of companies, from first pitch to renewal.", "#/t/partner_events": "Volunteering days and visits with companies. Use People to list who came.",
  "#/t/event_people": "Everyone who came to an office event, with hours.", "#/r/relations": "Your biggest donors, funders and companies, and who looks after each one.",
  "#/t/legacies": "People who may remember the trust in a will. Private; never share this list.", "#/t/outcomes": "Things a gift can buy, with a price. They show on your public Donate page.",
  "#/t/projects": "The list of your programmes with place, lead, budget and stage.", "#/r/projects": "Projects as cards, grouped by stage.", "#/t/beneficiaries": "The people you serve, with village, age group and service.",
  "#/r/journey": "Pick a person and see their whole story from joining to outcome.", "#/t/journey": "Add each step in a person's journey.", "#/t/activities": "Classes, camps and visits, with how many people were reached.",
  "#/r/gallery": "Event pictures, with consent marked.", "#/t/results": "Targets and what you achieved for each project.", "#/t/project_spend": "Budget against money used, by project.",
  "#/t/team": "Staff and volunteers, with pay type.", "#/t/attendance": "Mark who was present each day.", "#/t/volunteer_log": "Hours and travel given by volunteers.", "#/r/payroll": "Monthly pay worked out from attendance.",
  "#/t/grants": "Funders, the money sanctioned, and report due dates.", "#/r/grants": "Received, spent and balance for each grant.", "#/t/tranches": "Instalments you are waiting for. Late ones are flagged.",
  "#/t/instalments": "Money actually received from funders.", "#/t/grant_spend": "Spending against each grant, with bills kept or missing.", "#/t/funds": "General, restricted and corpus funds with opening balances.",
  "#/t/cash_book": "Every receipt and payment in one list.", "#/r/claims": "Staff expense claims to approve and pay.", "#/r/bank": "Upload a bank statement and match each line to your records.",
  "#/r/funds": "The balance in each fund at a glance.", "#/r/trustee": "A summary for your trustees.", "#/t/compliance": "Due dates such as returns and renewals, with reminders.",
  "#/r/pack": "Receipts, the 80G list and the audit trail for your accountant. Your CA should check them.", "#/r/forecast": "Twelve months ahead, showing when free cash may run short.",
  "#/r/board": "A printable page for board meetings.", "#/t/decisions": "Decisions with an owner, a due date and a status.", "#/r/budget": "Quick calculators for budgets and camps.",
  "#/t/budget_lines": "Detailed cost lines for each project.", "#/t/appeals": "Fundraising drives: what each cost and what it raised.", "#/t/cashflow_plan": "Expected money in and out, month by month.",
  "#/r/impact": "A report that shows donors what their money did.", "#/r/csr": "A draft report for company funders.", "#/r/cards": "Make a private link that shows a month of work.",
  "#/r/allprojects": "One summary across every project.", "#/r/yearcheck": "A checklist of what to look at for the year: receipts, calendar, funders, backups, passwords, governance.",
  "#/r/riskmap": "Open risks placed by how likely and how bad.", "#/t/risks": "The things that could hurt the trust, who watches each, and what you do about it.", "#/t/incidents": "Safeguarding concerns, accidents and complaints. Administrators only.",
  "#/t/social_posts": "Plan, approve and track social media posts.", "#/r/social": "Post ideas and caption drafts taken from your own records.", "#/r/yearplan": "The next 12 months of festivals, company steps and due dates in one list.", "#/t/plan_calendar": "Festivals, awareness days and giving windows with a campaign for each.", "#/t/csr_pipeline": "Companies you are talking to about CSR, employee giving, matching or volunteering.", "#/t/policies": "The written policies you need, with adoption and review dates.", "#/t/trustees": "Your trustees and members and when they joined.", "#/t/meetings": "Board, AGM and committee meetings with minutes.", "#/r/formats": "Printable forms and letters.", "#/t/records": "Meetings, letters and other records.", "#/t/record_lines": "The items inside each record.", "#/r/help": "This page.",
  "#/a/branding": "Your name, logo and colours.", "#/a/settings": "Organisation details, reminders, message provider keys and public pages.", "#/a/lists": "Edit the choices in dropdown menus.",
  "#/a/users": "Add staff and choose what each person can see.", "#/a/audit": "Download a protected backup, or restore one. Photos are not in the backup; copy the media folder separately.", "#/a/auditlog": "A record of who changed what, and when." };
const HOWTO = [
  ["Add my own contact", "Open Contacts, press + Add, fill in the name and phone, set OK to send WhatsApp to Y only if they agreed, and save. To add many, press Import CSV."],
  ["Send a message to many people", "Open Broadcast. Choose how (WhatsApp, SMS or email), who (a group or all donors), write the message, then Send now or schedule it. With no provider connected, use my own phone."],
  ["Add a user", "Open Admin, then Users, and press + Add. Choose a role: administrator, accounts, programme or view only. Ask them to change the password on first sign-in."],
  ["Bring in my old records", "Open the page (for example Donors), press Import CSV, use Blank template, fill it in, then Check file first. Fix any problems it lists, then press Import."],
  ["Share a donor's giving", "Open Donors, find the donor, press Giving page, and send the private link. Switch it off from the same place."],
  ["Show the public pages", "Open Admin, then Settings. Switch on the Donate page and the Transparency page. Add outcomes under Sponsor outcomes so donors can pick what to fund."],
  ["Back up my data", "Open Admin, then Backup & restore, and download a backup every week. Also copy the media folder if you keep photos."]];
async function viewHelp() {
  const q = h("input", { type: "search", placeholder: "Search the guide…", "aria-label": "Search the guide", style: "max-width:360px" });
  const out = h("div", {});
  const draw = () => {
    const s = q.value.trim().toLowerCase(), hit = t => !s || t.toLowerCase().includes(s);
    const how = HOWTO.filter(([a, b]) => hit(a + " " + b));
    const groups = NAV.map(([g, items]) => [g, items.filter(([l, href]) => HELP[href] && hit(l + " " + HELP[href]) && !(g === "Admin" && USER.role !== "admin"))]).filter(([, it]) => it.length);
    out.replaceChildren(how.length ? h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "How do I…"), ...how.map(([a, b]) => h("div", { style: "margin-bottom:8px" }, h("b", {}, a), h("div", {}, b)))) : null,
      ...groups.map(([g, items]) => h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, g), careTable([["Page"], ["What it is for"]], items.map(([l, href]) => h("tr", {}, h("td", {}, h("a", { href }, l)), h("td", {}, HELP[href])))))),
      !how.length && !groups.length ? h("div", { class: "empty" }, "Nothing matches. Try another word.") : null);
  };
  q.addEventListener("input", draw); draw();
  return h("div", {}, head("Help and page guide", "What each page is for, and how to do the common jobs. The Display button at the top changes light or dark and the accent colour."), h("div", { style: "margin-bottom:12px" }, q), out);
}
