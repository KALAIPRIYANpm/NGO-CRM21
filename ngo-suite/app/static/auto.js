/* Automation screens: status page, bank import, phone field entry, send-receipt dialog. */
"use strict";
const FIN_ROLES = ["admin", "accountant"];
const phoneDigits = p => { const d = String(p || "").replace(/\D/g, ""); return d.length === 10 ? "91" + d : d; };

async function sendReceipt(row) {
  const donor = await must(() => get("/t/donors/" + row.donor_id)); if (!donor) return;
  const msg = (META.settings.thanks_message || "").replace(/\{name\}/g, donor.name).replace(/\{amount\}/g, IN.format(row.amount)).replace(/\{receipt\}/g, row.receipt_no || "").replace(/\{org\}/g, META.settings.org_name || "").replace(/\{contact\}/g, [META.settings.org_phone, META.settings.org_email].filter(Boolean).join(" · "));
  const ph = phoneDigits(donor.phone);
  const body = h("div", {}, h("p", {}, h("b", {}, donor.name), " · ", money(row.amount), " · ", row.receipt_no), h("textarea", { rows: 4, readonly: true }, msg),
    h("p", { class: "hint" }, "WhatsApp and SMS open on your own phone or computer with the message ready; you press send. No paid service is used."),
    h("div", { class: "actions" },
      h("button", { class: "btn", onclick: () => close() }, "Close"),
      ph.length >= 11 ? h("a", { class: "btn", target: "_blank", rel: "noopener", href: `https://wa.me/${ph}?text=${encodeURIComponent(msg)}` }, "WhatsApp") : null,
      donor.phone ? h("a", { class: "btn", href: `sms:${donor.phone.replace(/[^\d+]/g, "")}?body=${encodeURIComponent(msg)}` }, "SMS") : null,
      h("button", { class: "btn pri", disabled: !donor.email || !META.settings.smtp_host, title: !donor.email ? "This donor has no email" : !META.settings.smtp_host ? "Set up email in Settings" : "", onclick: async () => {
        const r = await must(() => post(`/donations/${row.id}/email`, { force: true })); if (r) { toast("Receipt emailed"); close(); window._refreshRegister && window._refreshRegister(); } } }, "Email receipt")));
  const close = modal("Send receipt and thanks", body);
}

/* ---------------- automation status page ---------------- */
async function viewAutomation() {
  if (!FIN_ROLES.includes(USER.role)) return h("div", {}, head("Automations"), h("div", { class: "card" }, "Ask an administrator or the accounts officer."));
  const st = await get("/automation/status"), d = st.digest, S = META.settings;
  const on = k => S[k] === "Yes";
  const run = (k, label) => h("button", { class: "btn sm", disabled: USER.role !== "admin" || (k !== "backup" && !st.email_ready), title: USER.role !== "admin" ? "Administrators only" : !st.email_ready && k !== "backup" ? "Set up email in Settings first" : "",
    onclick: async () => { const r = await must(() => post("/automation/run/" + k)); if (r) toast(r.note || (r.sent != null ? `${r.sent} email(s) sent` : "Done"), r.ok === false); } }, label);
  const row = (name, flag, desc, btn) => h("tr", {}, h("td", {}, h("b", {}, name), h("div", { class: "hint" }, desc)), h("td", {}, flag === null ? "" : h("span", { class: "badge b-" + (flag ? "green" : "grey") }, flag ? "On" : "Off")), h("td", {}, btn));
  const list = (title, items) => items.length ? h("div", {}, h("b", {}, title), h("ul", { style: "margin:4px 0 10px 18px" }, ...items.map(x => h("li", {}, x)))) : null;
  return h("div", {}, head("Automations", "What runs by itself every day while the server is running. Switch each one on in Settings."),
    st.email_ready ? null : h("div", { class: "card", style: "margin-bottom:12px;border-color:var(--amber)" }, "Email is not set up yet, so nothing can be sent. Add your mail account in ", h("a", { href: "#/a/settings" }, "Settings"), ". Backups, bank import and calendars work without it."),
    h("div", { class: "tablewrap", style: "margin-bottom:14px" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Automation"), h("th", {}, "Status"), h("th", {}, "Run now"))), h("tbody", {},
      row("Morning digest", on("digest_auto"), "Calls due, receipts and thank-yous pending, lapsed donors, birthdays, compliance dates. Once a day.", run("digest", "Send now")),
      row("Deadline alerts", on("deadline_alerts_auto"), `Grant reports and compliance dates, at ${S.grant_alert_days} days. Each alert is sent once.`, run("deadlines", "Send now")),
      row("Receipt and thank-you email", on("auto_receipt_email"), "Sent the moment a donation is saved, if the donor has an email.", null),
      row("Birthday wishes", S.birthday_auto === "Yes", "See the Birthdays page.", null),
      row("Trustee report", on("trustee_report_auto"), "Previous month, emailed once on or after the report day.", run("trustee", "Send now")),
      row("Donor impact reports", on("impact_auto"), "Every quarter to donors whose gifts went to a project with results.", run("impact", "Send now")),
      row("Daily backup", on("backup_auto"), "Last: " + (st.last_backup || "none yet") + (S.backup_copy_dir ? " · copy folder " + S.backup_copy_dir : " · no second copy folder set"), run("backup", "Back up now"))))),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", {}, "Today's digest preview"), d.empty ? h("div", { class: "empty" }, "Nothing needs attention today.") : h("div", {},
        list("Needs attention", d.alerts.map(a => a.text)), list("Donors to call", d.calls.map(x => `${x.name} ${x.phone || ""}`)), list("Receipts to give", d.receipts.map(x => `${x.receipt_no} ${x.name}`)), list("Thank-yous to send", d.thanks.map(x => `${x.receipt_no} ${x.name}`)),
        list("Not given for a year", d.lapsed.map(x => `${x.name} (last gift ${fd(x.last_gift)})`)), list("Compliance", d.compliance.map(x => `${x.title}: ${x.cstatus} (${fd(x.next_due)})`)))),
      h("div", { class: "card" }, h("h2", {}, "Donate page and QR"), h("p", { class: "hint" }, S.org_upi ? "Your UPI ID: " + S.org_upi : "Add your UPI ID in Settings to enable this."),
        S.org_upi ? h("div", {}, h("img", { src: "/api/qr.svg?text=" + encodeURIComponent(upiLink({ upi: S.org_upi, name: S.org_name })), alt: "UPI QR code", style: "width:160px;height:160px;display:block;margin-bottom:8px" }),
          h("div", { class: "actions", style: "justify-content:flex-start" }, h("button", { class: "btn", onclick: () => showPrint("poster", { kind: "poster", org: { name: S.org_name, tagline: S.org_tagline, address: S.org_address, phone: S.org_phone, email: S.org_email, reg: S.org_reg, upi: S.org_upi }, message: S.donate_message, qr: "/api/qr.svg?text=" + encodeURIComponent(upiLink({ upi: S.org_upi, name: S.org_name })) }) }, "Print QR poster"),
            h("a", { class: "btn", href: "/donate.html", target: "_blank", rel: "noopener" }, "Open Donate page")), h("p", { class: "hint" }, S.donate_page === "Yes" ? "Donate page is ON. Share the link: your server address + /donate.html. It needs to be reachable from the internet to be used by the public." : "Donate page is OFF (switch on in Settings).")) : null)));
}

/* ---------------- bank statement import ---------------- */
async function viewBank() {
  const funds = await get("/options/funds");
  const fundSel = h("select", {}, h("option", { value: "" }, "Choose fund…"), ...funds.map(f => h("option", { value: f.id }, f.label || f.name)));
  const out = h("div", {});
  const file = h("input", { type: "file", accept: ".csv,text/csv" });
  const paste = h("textarea", { rows: 4, placeholder: "…or paste the CSV text here" });
  let rows = [];
  const draw = () => {
    if (!rows.length) { out.replaceChildren(); return; }
    const sum = a => rows.filter(r => r.action === a).length;
    const t = h("table", {}, h("thead", {}, h("tr", {}, ...["Date", "Narration", "In", "Out", "What to do", "Matched with"].map(x => h("th", {}, x)))), h("tbody", {}, ...rows.map(r => {
      const sel = h("select", { onchange: e => { r.action = e.target.value; draw(); } }, ...[["match", "Link to existing"], ["new", "Add as new entry"], ["skip", "Skip"]].filter(([v]) => v !== "match" || r.match).map(([v, l]) => h("option", { value: v, selected: r.action === v }, l)));
      if (r.duplicate) sel.disabled = true;
      return h("tr", { style: r.duplicate ? "opacity:.5" : "" }, h("td", {}, fd(r.date)), h("td", {}, r.narration + (r.ref ? " · " + r.ref : "")), h("td", { class: "n" }, r.type === "Receipt" ? money(r.amount) : ""), h("td", { class: "n" }, r.type === "Payment" ? money(r.amount) : ""),
        h("td", {}, r.duplicate ? "Already imported" : sel), h("td", {}, r.match ? [r.match.label, " ", h("span", { class: "badge b-" + (r.match.confidence === "high" ? "green" : "amber") }, r.match.confidence)] : ""));
    })));
    out.replaceChildren(h("div", { class: "bar" }, h("b", {}, `${rows.length} lines: ${sum("match")} to link, ${sum("new")} new, ${sum("skip")} skipped`), h("span", { class: "grow" }), fundSel,
      h("button", { class: "btn pri", onclick: async () => {
        const items = rows.map(r => ({ hash: r.hash, date: r.date, amount: r.amount, type: r.type, narration: r.narration, ref: r.ref, action: r.action, match_kind: r.match && r.match.kind, match_id: r.match && r.match.id }));
        const res = await must(() => post("/bank/commit", { items, fund_id: fundSel.value || null })); if (!res) return;
        toast(`${res.matched} linked, ${res.created} added`); rows = []; draw();
        out.replaceChildren(h("div", { class: "card" }, h("b", {}, `${res.matched} linked, ${res.created} added, ${res.skipped} skipped.`), res.errors.length ? h("ul", { style: "margin:6px 0 0 18px;color:var(--red)" }, ...res.errors.map(e => h("li", {}, e))) : null));
      } }, "Import selected")), h("div", { class: "tablewrap" }, t));
  };
  const preview = async text => { const r = await must(() => post("/bank/preview", { csv: text })); if (r) { rows = r.rows; draw(); } };
  file.onchange = () => { const f = file.files[0]; if (!f) return; if (f.size > 5e6) return toast("File too large", true); const rd = new FileReader(); rd.onload = () => preview(String(rd.result)); rd.readAsText(f); };
  return h("div", {}, head("Bank statement import", "Download your statement as CSV from net banking. Lines that match a donation or payment you already recorded are linked, not double counted."),
    h("div", { class: "card", style: "margin-bottom:14px" }, h("div", { class: "bar" }, file, h("button", { class: "btn", onclick: () => paste.value.trim() && preview(paste.value) }, "Preview pasted text")), paste,
      h("p", { class: "hint" }, "Needs columns like Date, Narration, Debit or Withdrawal, Credit or Deposit (or Amount with Dr/Cr). Nothing is saved until you press Import. Importing the same statement twice is safe: repeated lines are ignored.")), out);
}

/* ---------------- phone field page: attendance + new person, works offline ---------------- */
const QKEY = "ngo_field_queue";
const qGet = () => { try { return JSON.parse(localStorage.getItem(QKEY) || "[]"); } catch (e) { return []; } };
const qSet = a => { try { localStorage.setItem(QKEY, JSON.stringify(a)); } catch (e) { /* storage blocked: queue stays in memory only */ } };
async function flushQueue() {
  if (flushQueue.busy) return { done: 0, left: qGet().length };
  flushQueue.busy = true;
  let q = qGet(), left = [], done = 0, rejected = [];
  try {
    for (const it of q) { try { await api("POST", it.path, it.body); done++; } catch (e) { if (e.status && e.status < 500) rejected.push(e.message); else left.push(it); } }
    qSet(left);
  } finally { flushQueue.busy = false; }
  if (rejected.length) toast("Server refused " + rejected.length + " waiting item(s): " + rejected[0], true);
  return { done, left: left.length };
}
async function viewField() {
  const w = h("div", { class: "field" });
  const msg = h("div", { class: "hint", "aria-live": "polite" });
  const proj = await projectOptions(), villages = (META.lists.village || []), ages = META.lists.age_group || [], services = META.lists.service || [];
  const updateMsg = () => { const n = qGet().length; msg.textContent = n ? `${n} item(s) waiting to upload. They will be sent when the network is back.` : "All saved."; };
  async function send(path, body) {
    try { await api("POST", path, body); return "saved"; }
    catch (e) { if (e.status === 0 || e.status >= 500 || /fetch|network/i.test(e.message)) { const q = qGet(); q.push({ path, body }); qSet(q); return "queued"; } throw e; }
  }
  const team = await (async () => { try { return await get("/field/team"); } catch (e) { return null; } })();
  const att = h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "Attendance today" + (team ? " · " + fd(team.date) : "")));
  if (team) for (const m of team.team) {
    const btns = {};
    const set = async v => { const r = await must(() => send("/attendance/mark", { team_id: m.id, date: team.date, attendance: v })); if (r) { Object.entries(btns).forEach(([k, b]) => b.classList.toggle("pri", k === v)); toast(r === "queued" ? "Saved on this phone; will upload later" : "Saved"); updateMsg(); } };
    att.append(h("div", { style: "display:flex;gap:6px;align-items:center;padding:6px 0;border-top:1px solid var(--line)" }, h("div", { style: "flex:1" }, h("b", {}, m.name), h("div", { class: "hint" }, m.role || "")),
      ...[["P", "Present"], ["H", "Half"], ["A", "Absent"]].map(([k, l]) => btns[k] = h("button", { class: "btn" + (m.att === k ? " pri" : ""), style: "min-width:64px;padding:10px", onclick: () => set(k) }, l))));
  } else att.append(h("div", { class: "empty" }, "Could not load the team (no network?). Open this page once while online."));
  const f = {}, dupBox = h("div", {});
  const inp = (k, l, el) => { f[k] = el; return h("div", {}, h("label", {}, l), el); };
  const sel = (opts, blank) => h("select", {}, h("option", { value: "" }, blank || "Choose…"), ...opts.map(o => h("option", { value: o.value ?? o }, o.label ?? o)));
  const checkDup = async () => {
    try { const r = await get(`/duplicates?name=${encodeURIComponent(f.name.value)}&village=${encodeURIComponent(f.village.value)}&phone=${encodeURIComponent(f.phone.value)}`);
      dupBox.replaceChildren(r.length ? h("div", { class: "card", style: "border-color:var(--amber);margin-top:8px" }, h("b", {}, "This person may already be registered:"), ...r.map(x => h("div", {}, `${x.kind}: ${x.name} ${x.phone || ""} (${x.reason})`))) : ""); return r; } catch (e) { return []; }
  };
  const form = h("div", { class: "card" }, h("h2", {}, "Add a person served"),
    h("div", { class: "inputgrid" }, inp("name", "Name", h("input", { autocomplete: "off" })), inp("phone", "Phone", h("input", { type: "tel", inputmode: "tel" })), inp("village", "Village or ward", sel(villages)),
      inp("gender", "Gender", sel(["Female", "Male", "Other"])), inp("age_group", "Age group", sel(ages)), inp("project_id", "Project", sel(proj.map(p => ({ value: p.id, label: p.label || p.name })))), inp("service", "Service", sel(services))),
    dupBox, h("div", { class: "actions" }, h("button", { class: "btn", onclick: checkDup }, "Check for duplicates"), h("button", { class: "btn pri", onclick: async () => {
      if (!f.name.value.trim()) return toast("Enter a name", true);
      if (!f.project_id.value) return toast("Choose a project", true);
      const dups = await checkDup();
      if (dups.length && !form.dataset.ok) { form.dataset.ok = "1"; return toast("Possible duplicate shown. Press Save again if this is a new person.", true); }
      const body = { name: f.name.value.trim(), phone: f.phone.value.trim(), village: f.village.value, gender: f.gender.value, age_group: f.age_group.value, project_id: f.project_id.value, service: f.service.value, date_joined: asofISO(), status: "Active" };
      const r = await must(() => send("/t/beneficiaries", body)); if (!r) return;
      toast(r === "queued" ? "Saved on this phone; will upload later" : "Saved"); delete form.dataset.ok; Object.values(f).forEach(e => e.value = ""); dupBox.replaceChildren(); updateMsg();
    } }, "Save")));
  w.append(head("Field entry", "Big buttons for the phone. If the network drops, entries wait on this phone and upload later."), msg, att, form);
  updateMsg();
  const sync = async () => { if (!qGet().length) return; const r = await flushQueue(); if (r.done) toast(`${r.done} waiting item(s) uploaded`); updateMsg(); };
  window._fieldSync = sync;
  if (!window._fieldOnline) { window._fieldOnline = true; window.addEventListener("online", () => window._fieldSync && window._fieldSync()); }
  sync();
  return w;
}
