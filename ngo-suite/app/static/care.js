/* v8 screens: giving promises, slipping donors, beneficiary journey, duplicates, funder report, weekly summary,
   password-protected backups and restore, and the searchable audit trail. */
"use strict";
const CST = { Late: "red", "Due soon": "amber", "Due now": "amber", "On track": "green", Paused: "grey", Ended: "grey", Lapsed: "red", Slipping: "amber", "Due for a thank-you or update": "blue" };
const careTile = (n, l) => h("div", { class: "stat" }, h("div", { class: "sl" }, l), h("div", { class: "sv" }, n));
const careTiles = (...t) => h("div", { class: "stats" }, ...t);
const careTable = (cols, rows, empty) => rows.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...cols.map(c => h("th", { class: c[1] || "" }, c[0])))), h("tbody", {}, ...rows))) : h("div", { class: "empty" }, empty);
const pill = (t, c) => h("span", { class: "badge b-" + (c || CST[t] || "grey") }, t);
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); toast("Message copied"); }
  catch (e) { const ta = h("textarea", { style: "position:fixed;opacity:0" }, t); document.body.append(ta); ta.select(); try { document.execCommand("copy"); toast("Message copied"); } catch (e2) { toast("Could not copy. Select the text and copy it.", true); } ta.remove(); }
}
function msgButtons(r) {
  return [r.wa ? h("a", { class: "btn sm", href: r.wa, target: "_blank", rel: "noopener" }, "WhatsApp") : null, r.wa ? " " : null,
    h("button", { class: "btn sm", onclick: () => modal("Message for " + (r.donor || r.name), h("div", {}, h("textarea", { rows: 6, readonly: true, onfocus: e => e.target.select() }, r.message), h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => copyText(r.message) }, "Copy"), r.wa ? h("a", { class: "btn pri", href: r.wa, target: "_blank", rel: "noopener" }, "Open in WhatsApp") : null))) }, "Message")];
}

/* ---------------- regular giving promises ---------------- */
async function viewPromises() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Giving promises"), h("div", { class: "card" }, "Not available for your role."));
  const d = await get("/care/promises"), s = d.summary;
  const rows = d.items.map(r => h("tr", {}, h("td", {}, r.donor, h("div", { class: "hint" }, r.donor_code)), h("td", { class: "n" }, money(r.amount), h("div", { class: "hint" }, r.frequency)), h("td", {}, pill(r.status)),
    h("td", {}, fd(r.next_due)), h("td", {}, fd(r.last_paid)), h("td", { class: "n" }, r.missed || ""), h("td", { class: "n" }, r.owed ? money(r.owed) : ""),
    h("td", {}, r.message ? msgButtons(r) : null, r.message ? " " : null, h("button", { class: "btn sm", onclick: () => openForm("commitments", r, null, () => route()) }, "Edit"))));
  return h("div", {}, head("Giving promises", "Donors who promised to give every month, quarter or year, matched against the donations you record."),
    careTiles(careTile(s.active, "active promises"), careTile(s.late, "late"), careTile(s.due, "due this week"), careTile(money(s.owed), "not yet received"), careTile(money(s.monthly_value), "promised each month")),
    h("div", { class: "actions noprint", style: "margin-bottom:10px" }, h("button", { class: "btn pri", onclick: () => openForm("commitments", null, {}, () => route()) }, "Add a promise"), h("a", { class: "btn", href: "#/t/commitments" }, "See as a list")),
    careTable([["Donor"], ["Each time", "n"], ["Status"], ["Next due"], ["Last paid"], ["Missed", "n"], ["Owed", "n"], [""]], rows, "No regular-giving promises yet. Press Add a promise."),
    h("p", { class: "hint" }, "A promise counts as paid when a donation from that donor of at least 90% of the amount is recorded within the period. A promise is Late a week after its due date. Turn on automatic email reminders in Settings → Automation."));
}

/* ---------------- donors slipping away ---------------- */
async function viewLapse() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Donors slipping away"), h("div", { class: "card" }, "Not available for your role."));
  const d = await get("/care/lapse");
  const rows = d.donors.map(r => h("tr", {}, h("td", {}, h("a", { href: "#/t/donors" }, r.name), h("div", { class: "hint" }, r.code + (r.language ? " · " + r.language : ""))), h("td", {}, pill(r.status)),
    h("td", {}, fd(r.last_gift), h("div", { class: "hint" }, money(r.last_amount))), h("td", { class: "n" }, r.days_since + " d", h("div", { class: "hint" }, "usual gap " + r.cadence_days + " d")),
    h("td", { class: "n" }, money(r.total), h("div", { class: "hint" }, r.gifts + " gift" + (r.gifts === 1 ? "" : "s"))),
    h("td", {}, msgButtons(r), " ", h("button", { class: "btn sm", onclick: async () => { if (await must(() => post("/care/followup", { donor_id: r.id }))) toast("Added to today's follow-ups"); } }, "Follow up"))));
  return h("div", {}, head("Donors slipping away", "Each donor is compared with their own giving rhythm, so a yearly donor is not flagged after three months."),
    careTiles(careTile(d.summary.Due, "due a thank-you or update"), careTile(d.summary.Slipping, "slipping"), careTile(d.summary.Lapsed, "lapsed"), careTile(money(d.value_at_risk), "average gift of those slipping or lapsed")),
    careTable([["Donor"], ["Status"], ["Last gift"], ["Since", "n"], ["Given", "n"], [""]], rows, "Every donor is giving on their usual rhythm. Good news."),
    h("p", { class: "hint" }, "How it works: the usual gap is the middle value of the gaps between that donor's gifts (a donor with one gift is assumed to give yearly). Due = past the usual gap; Slipping = " + d.factor + " times the usual gap; Lapsed = well beyond. Donors with an active giving promise are on the promises page instead. WhatsApp opens a chat from your own phone with the message ready; only use it for people who agreed to be contacted. Messages are in the donor's preferred language (set it on the donor) and should be read before sending."));
}

/* ---------------- beneficiary journey ---------------- */
const JST = { Enrolled: "blue", Assessed: "blue", "Service started": "blue", "Service given": "green", "Follow-up visit": "grey", "Milestone reached": "amber", "Outcome achieved": "green", Referred: "grey", Exited: "grey", "Dropped out": "red" };
async function journeyTimeline(id, after) {
  const t = await must(() => get("/journey/timeline/" + id)); if (!t) return;
  const p = t.person;
  const steps = h("div", { class: "jline" }, ...t.events.map(e => h("div", { class: "jstep" }, h("div", { class: "jdot" }), h("div", { class: "jbody" }, h("div", {}, h("b", {}, fd(e.date)), " ", pill(e.stage, JST[e.stage] || "grey"), e.implied ? h("span", { class: "hint" }, " (from the joining date)") : null),
    e.detail ? h("div", {}, e.detail) : null, e.outcome ? h("div", {}, "Outcome: ", h("b", {}, e.outcome)) : null, e.recorded_by ? h("div", { class: "hint" }, "by " + e.recorded_by) : null))));
  const note = t.closed ? h("div", { class: "qbar" }, "This journey is closed: " + t.closed + ".") : t.days_quiet != null && t.days_quiet > 45 ? h("div", { class: "qbar warn" }, "No step recorded for " + t.days_quiet + " days.") : null;
  const close = modal(p.name + " · " + (p.code || ""), h("div", {}, h("div", { class: "hint" }, [p.project, p.village, p.gender, p.age_group].filter(Boolean).join(" · ")), note,
    t.next_step ? h("div", { class: "hint", style: "margin:6px 0" }, "Next usual step: ", h("b", {}, t.next_step)) : null, steps,
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Close"), can("journey") ? h("button", { class: "btn pri", onclick: () => { close(); openForm("journey", null, { beneficiary_id: id, date: asofISO(), stage: t.next_step || "Follow-up visit" }, () => { journeyTimeline(id, after); if (after) after(); }); } }, "Add a step") : null)), { wide: true });
}
async function viewJourney() {
  const proj = await get("/options/projects"); let tab = "people";
  const pSel = h("select", {}, h("option", { value: "" }, "All projects"), ...proj.map(p => h("option", { value: p.id }, p.label || p.name)));
  const q = h("input", { type: "search", placeholder: "Find a person by name, ID or village", style: "max-width:320px" });
  const body = h("div", {}), tabs = h("div", { class: "tabs", role: "tablist" });
  const draw = async () => {
    tabs.replaceChildren(...[["people", "People"], ["funnel", "Progress"], ["stale", "Needs a visit"]].map(([k, l]) => h("button", { class: "tab" + (tab === k ? " on" : ""), role: "tab", "aria-selected": tab === k, onclick: () => { tab = k; draw(); } }, l)));
    const pq = pSel.value ? "project_id=" + pSel.value : "";
    if (tab === "people") {
      const rows = (await get("/journey/people?" + pq + "&q=" + encodeURIComponent(q.value))).map(r => h("tr", { style: "cursor:pointer", onclick: () => journeyTimeline(r.id, draw) }, h("td", {}, r.name, h("div", { class: "hint" }, r.code)), h("td", {}, r.project), h("td", {}, r.village), h("td", {}, r.last_stage ? pill(r.last_stage, JST[r.last_stage] || "grey") : h("span", { class: "hint" }, "no steps yet")), h("td", { class: "n" }, r.steps)));
      body.replaceChildren(q, careTable([["Person"], ["Project"], ["Village"], ["Latest step"], ["Steps", "n"]], rows, "No one found. Add people under Beneficiaries."));
    } else if (tab === "funnel") {
      const s = await get("/journey/summary?" + pq), mx = Math.max(1, ...s.funnel.map(f => f.count));
      body.replaceChildren(careTiles(careTile(s.total, "people enrolled"), careTile((s.funnel.find(f => f.stage === "Outcome achieved") || {}).count || 0, "reached an outcome"), careTile(s.exited, "exited or dropped out")),
        h("div", { class: "card" }, h("h2", {}, "How far people have come"), ...s.funnel.map(f => h("div", { class: "frow" }, h("div", { class: "fl" }, f.stage), h("div", { class: "fbar" }, h("div", { style: `width:${Math.round(f.count / mx * 100)}%` })), h("div", { class: "fn" }, f.count)))),
        s.outcomes.length ? h("div", { class: "card", style: "margin-top:12px" }, h("h2", {}, "Outcomes recorded"), h("ul", {}, ...s.outcomes.map(o => h("li", {}, o.outcome + " (" + o.n + ")")))) : null);
    } else {
      const s = await get("/journey/stale?" + pq);
      const rows = s.people.map(r => h("tr", { style: "cursor:pointer", onclick: () => journeyTimeline(r.id, draw) }, h("td", {}, r.name, h("div", { class: "hint" }, r.code)), h("td", {}, r.project), h("td", {}, r.village), h("td", {}, r.phone), h("td", { class: "n" }, r.days_quiet == null ? "–" : r.days_quiet + " days")));
      body.replaceChildren(h("p", { class: "hint" }, s.count + " active people have had no recorded step for " + s.days + " days or more. Change the number of days in Settings."), careTable([["Person"], ["Project"], ["Village"], ["Phone"], ["Quiet for", "n"]], rows, "Everyone has been seen recently."));
    }
  };
  pSel.onchange = draw; q.oninput = () => { clearTimeout(q.t); q.t = setTimeout(draw, 300); };
  await draw();
  return h("div", {}, head("Beneficiary journey", "Follow each person from joining to outcome. Click a person to see their timeline.", pSel), tabs, body,
    can("journey") ? h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => openForm("journey", null, { date: asofISO() }, draw) }, "Add a step for anyone"), h("a", { class: "btn", href: "#/t/journey" }, "All steps as a list")) : null);
}

/* ---------------- duplicates ---------------- */
async function viewDups() {
  const roles = USER.role; const kinds = [];
  if (["admin", "accountant"].includes(roles)) kinds.push(["donors", "Donors"]);
  if (["admin", "programme"].includes(roles)) kinds.push(["beneficiaries", "People served"]);
  if (!kinds.length) return h("div", {}, head("Find duplicates"), h("div", { class: "card" }, "Not available for your role."));
  let kind = kinds[0][0]; const body = h("div", {}), tabs = h("div", { class: "tabs" });
  const scan = async () => {
    tabs.replaceChildren(...kinds.map(([k, l]) => h("button", { class: "tab" + (kind === k ? " on" : ""), onclick: () => { kind = k; scan(); } }, l)));
    body.replaceChildren(h("div", { class: "empty" }, "Looking for duplicates…"));
    const r = await must(() => get("/dedupe/scan?kind=" + kind)); if (!r) return;
    if (!r.groups.length) return body.replaceChildren(h("div", { class: "card" }, "No duplicates found. Matches are by phone number, email, and the same or very similar name in the same place."));
    body.replaceChildren(h("p", { class: "hint" }, r.count + " possible duplicate group" + (r.count === 1 ? "" : "s") + ". Check each one; they may be different people. Merging moves all history to the record you keep and cannot be undone (the merge is written to the audit trail)."),
      ...r.groups.map(g => {
        let keep = g.suggested_keep; const drop = new Set(g.records.filter(x => x.id !== keep).map(x => x.id)); const rows = [];
        const redraw = () => rows.forEach(f => f());
        const trs = g.records.map(x => {
          const rad = h("input", { type: "radio", name: "k" + g.records[0].id, checked: x.id === keep, onchange: () => { const prev = keep; keep = x.id; drop.delete(x.id); drop.add(prev); redraw(); } });
          const ck = h("input", { type: "checkbox", onchange: e => { e.target.checked ? drop.add(x.id) : drop.delete(x.id); } });
          rows.push(() => { ck.disabled = keep === x.id; ck.checked = drop.has(x.id); });
          const facts = kind === "donors" ? `${x.donations} gifts · ${money(x.total)} · ${x.notes} notes` : `${x.steps} journey steps`;
          return h("tr", {}, h("td", {}, rad), h("td", {}, ck), h("td", {}, x.name, h("div", { class: "hint" }, x.code)), h("td", {}, [x.phone, x.email].filter(Boolean).join(" · ")), h("td", {}, x[kind === "donors" ? "city" : "village"]), h("td", {}, facts));
        });
        redraw();
        return h("div", { class: "card", style: "margin-bottom:12px" }, h("div", {}, ...g.reasons.map(x => [pill(x, "amber"), " "])), g.conflict ? h("div", { class: "qbar warn" }, g.conflict) : null,
          h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Keep"), h("th", {}, "Merge in"), h("th", {}, "Name"), h("th", {}, "Contact"), h("th", {}, "Place"), h("th", {}, "History"))), h("tbody", {}, ...trs))),
          h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: () => { if (!drop.size) return toast("Tick at least one record to merge in", true); confirmBox(`Merge ${drop.size} record(s) into the one you chose to keep? This cannot be undone.`, async () => { const m = await must(() => post("/dedupe/merge", { kind, keep, drop: [...drop] })); if (m) { toast("Merged into " + m.kept); scan(); } }, "Merge"); } }, "Merge into the kept record")));
      }));
  };
  await scan();
  return h("div", {}, head("Find duplicates", "People entered twice, found by phone, email or a very similar name in the same place."), tabs, body);
}

/* ---------------- funder / CSR report ---------------- */
async function viewCsr() {
  if (!["admin", "accountant", "programme"].includes(USER.role)) return h("div", {}, head("Funder report"), h("div", { class: "card" }, "Not available for your role."));
  const proj = await get("/options/projects"), y = Number(asofISO().slice(0, 4)), m = Number(META.settings.fy_start_month || 4), cur = Number(asofISO().slice(5, 7));
  const fyY = cur >= m ? y : y - 1, from0 = fyY + "-" + String(m).padStart(2, "0") + "-01";
  const pSel = h("select", {}, ...proj.map(p => h("option", { value: p.id }, p.label || p.name))), a = h("input", { type: "date", value: from0 }), b = h("input", { type: "date", value: asofISO() });
  const notes = h("textarea", { rows: 4, maxlength: 1500, placeholder: "Anything you want to add for the funder: challenges, learning, plans for the next period…" });
  return h("div", {}, head("Funder report (CSR)", "A ready project report for a company funder or foundation, made from your own records."),
    h("div", { class: "card" }, h("div", { class: "inputgrid" }, h("div", {}, h("label", {}, "Project"), pSel), h("div", {}, h("label", {}, "From"), a), h("div", {}, h("label", {}, "To"), b)),
      h("label", { style: "margin-top:8px" }, "Your notes (printed at the end)"), notes,
      h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: () => { if (!pSel.value) return toast("Choose a project", true); window.open(`/api/csr?project_id=${pSel.value}&from=${a.value}&to=${b.value}&notes=${encodeURIComponent(notes.value)}`, "_blank", "noopener"); } }, "Open the report"))),
    h("div", { class: "card", style: "margin-top:12px" }, h("h2", {}, "What it contains"), h("ul", {}, h("li", {}, "Project details, purpose, people reached, activities, cost per person"), h("li", {}, "Targets and results, month by month work, people served by gender and age"),
      h("li", {}, "Beneficiary journey progress and recorded outcomes"), h("li", {}, "Budget against use by head, and each linked grant's received and unspent amounts"), h("li", {}, "Your story from the field, and up to six photos (only photos with consent)")),
      h("p", { class: "hint" }, "It opens in a new tab: press Ctrl+P to print or save as PDF. It is a draft: read every figure, and use your funder's own format if they have one. Your CA certifies the accounts.")));
}

/* ---------------- weekly manager summary ---------------- */
async function viewWeekly() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Weekly summary"), h("div", { class: "card" }, "Not available for your role."));
  const d = await get("/weekly"), w = d.week;
  const col = { red: "#b3261e", amber: "#b26a00", blue: "#1d4f8f" };
  return h("div", {}, head("Weekly summary", "What needs a decision this week. It can also be emailed to you every Monday."),
    careTiles(careTile(w.donations, "gifts this week"), careTile(money(w.donated), "received"), careTile(w.new_people, "new people enrolled"), careTile(w.activities, "activities"), careTile(num(w.reached), "people reached")),
    d.clear ? h("div", { class: "card" }, "Nothing needs your attention this week. Well done.") : h("div", { class: "card" }, h("h2", {}, "Needs your attention"), ...d.items.map(i => h("div", { style: "display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #eee" }, h("span", { style: `color:${col[i.level]};font-size:18px;line-height:1.2`, "aria-label": i.level }, i.level === "red" ? "●" : i.level === "amber" ? "◐" : "○"), h("div", { style: "flex:1" }, i.text), i.link ? h("a", { href: i.link }, "Open") : null))),
    h("div", { class: "actions" }, USER.role === "admin" ? h("button", { class: "btn", onclick: async () => { const r = await must(() => post("/weekly/send")); if (r) toast(r.note || `Sent ${r.sent}${r.failed ? ", failed " + r.failed : ""}`, !!r.failed); } }, "Email it now") : null, h("a", { class: "btn", href: "#/a/settings" }, "Set up Monday emails")),
    h("p", { class: "hint" }, "Red = something overdue or stalled. Grey-blue = for information. Set the recipients and switch on Monday emails in Settings → Automation."));
}

/* ---------------- password-protected backup and restore (used on the Backup & audit page) ---------------- */
async function backupCard() {
  const lst = await get("/backup/list"), pw = h("input", { type: "password", autocomplete: "new-password", placeholder: "Backup password (8+ characters)" });
  const dl = async () => {
    if (pw.value.length < 8) return toast("Use a password of at least 8 characters", true);
    const r = await fetch("/api/backup/encrypted", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: pw.value }), credentials: "same-origin" });
    if (!r.ok) { let m = "Could not make the backup"; try { m = (await r.json()).error || m; } catch (e) { /* keep */ } return toast(m, true); }
    const a = h("a", { href: URL.createObjectURL(await r.blob()), download: "ngo-backup-" + todayISO() + ".ngobk" }); document.body.append(a); a.click(); a.remove(); toast("Protected backup downloaded");
  };
  const file = h("input", { type: "file", accept: ".ngobk,.db" }), rpw = h("input", { type: "password", placeholder: "Backup password (for .ngobk files)" }), apw = h("input", { type: "password", placeholder: "Your administrator password", autocomplete: "current-password" }), conf = h("input", { placeholder: "Type RESTORE to confirm" });
  const restore = async () => {
    if (!file.files[0]) return toast("Choose a backup file first", true);
    if (conf.value !== "RESTORE") return toast("Type the word RESTORE to confirm", true);
    const r = await fetch("/api/backup/restore", { method: "POST", headers: { "X-Confirm": "RESTORE", "X-Admin-Password": apw.value, "X-Backup-Password": rpw.value }, body: file.files[0], credentials: "same-origin" });
    let j = {}; try { j = await r.json(); } catch (e) { /* keep */ }
    if (!r.ok) return toast(j.error || "Restore failed. Nothing was changed.", true);
    modal("Restored", h("div", {}, h("p", {}, `The backup was restored: ${j.counts.donors} donors, ${j.counts.donations} donations, ${j.counts.beneficiaries} people served.`), h("p", { class: "hint" }, "A copy of what was here before is saved on the server as " + j.safety_copy + ". Everyone has been signed out, and passwords are those from the backup."), h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: () => location.reload() }, "Sign in again"))));
  };
  return h("div", {}, h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, "Password-protected backup"), h("p", {}, "Download everything in one locked file, safe to keep on a pen drive or email to yourself. It includes your saved mail and WhatsApp keys, so a restore on a new computer works fully. Photos and videos are not inside: copy the data/media folder too."),
      h("div", { class: "bar" }, pw, h("button", { class: "btn pri", onclick: dl }, "Download protected backup")), h("p", { class: "hint" }, "Keep the password somewhere safe. If it is lost, the file cannot be opened by anyone, including us. To lock the automatic daily backups too, turn it on in Settings → Automation.")),
    h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, "Backups saved on this computer"), lst.files.length ? careTable([["File"], ["Type"], ["Size", "n"], [""]], lst.files.map(f => h("tr", {}, h("td", {}, f.name), h("td", {}, f.protected ? pill("password-protected", "green") : pill("not protected", "amber")), h("td", { class: "n" }, Math.round(f.size / 1024) + " KB"), h("td", {}, h("a", { class: "btn sm", href: "/api/backup/file/" + f.name }, "Download")))), "") : h("div", { class: "hint" }, "None yet. Press Save a copy on the server now above."),
      lst.encrypted ? null : h("p", { class: "hint" }, "Automatic backups are not password-protected. Anyone who can copy the file can read it. Turn protection on in Settings → Automation.")),
    h("div", { class: "card", style: "margin-bottom:14px;border-color:#b3261e" }, h("h2", {}, "Restore from a backup"), h("p", {}, "This replaces ALL current data with the backup. A safety copy of today's data is saved first. Everyone is signed out afterwards, and passwords go back to those in the backup."),
      h("div", { class: "inputgrid" }, h("div", {}, h("label", {}, "Backup file (.ngobk or .db)"), file), h("div", {}, h("label", {}, "Backup password"), rpw), h("div", {}, h("label", {}, "Your password"), apw), h("div", {}, h("label", {}, "Confirm"), conf)),
      h("div", { class: "actions" }, h("button", { class: "btn danger", onclick: () => confirmBox("Replace all current data with this backup?", restore, "Restore") }, "Restore this backup"))));
}

/* ---------------- audit trail ---------------- */
async function viewAuditLog() {
  const st = { offset: 0 }, body = h("div", {}), f = {};
  const mk = (k, el) => { f[k] = el; return el; };
  const q = mk("q", h("input", { type: "search", placeholder: "Search names, numbers, words…" })), from = mk("from", h("input", { type: "date" })), to = mk("to", h("input", { type: "date" }));
  const sel = (k, label) => mk(k, h("select", { "aria-label": label }, h("option", { value: "" }, label)));
  const su = sel("user", "Anyone"), sa = sel("action", "Any action"), sr = sel("tbl", "Any register");
  let rowId = ""; const qs = (extra = {}) => { const p = new URLSearchParams(); for (const k in f) if (f[k].value) p.set(k, f[k].value); if (rowId) p.set("row_id", rowId); for (const k in extra) p.set(k, extra[k]); return p.toString(); };
  let faceted = false;
  const draw = async () => {
    const r = await must(() => get("/auditlog?" + qs({ limit: 50, offset: st.offset }))); if (!r) return;
    if (!faceted) { faceted = true; r.facets.users.forEach(x => su.append(h("option", { value: x }, x))); r.facets.actions.forEach(x => sa.append(h("option", { value: x }, x))); r.facets.tables.forEach(x => sr.append(h("option", { value: x }, x))); }
    const rows = r.rows.map(x => h("tr", {}, h("td", { style: "white-space:nowrap" }, x.ts.replace("T", " ")), h("td", {}, x.user), h("td", {}, x.action), h("td", {}, x.tbl), h("td", { class: "n" }, x.row_id == null ? "" : h("a", { href: "#", title: "Everything that happened to this record", onclick: e => { e.preventDefault(); rowId = x.row_id; sr.value = x.tbl; st.offset = 0; draw(); } }, x.row_id)),
      h("td", { style: "max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer", title: "Click to read all", onclick: () => modal("Change details", h("pre", { style: "white-space:pre-wrap;word-break:break-word" }, x.detail || "")) }, x.detail)));
    const end = Math.min(r.total, r.offset + r.rows.length);
    body.replaceChildren(rowId ? h("div", { class: "qbar" }, `Showing everything for record ${rowId}. `, h("a", { href: "#", onclick: e => { e.preventDefault(); rowId = ""; draw(); } }, "Show all")) : null,
      h("div", { class: "hint", style: "margin:6px 0" }, r.total ? `${r.offset + 1}–${end} of ${r.total}` : "Nothing matches."),
      careTable([["When"], ["Who"], ["Action"], ["Register"], ["Row", "n"], ["Detail"]], rows, "No changes match these filters."),
      h("div", { class: "actions" }, h("button", { class: "btn", disabled: r.offset === 0, onclick: () => { st.offset = Math.max(0, r.offset - 50); draw(); } }, "Newer"), h("button", { class: "btn", disabled: end >= r.total, onclick: () => { st.offset = r.offset + 50; draw(); } }, "Older"), h("a", { class: "btn", href: "/api/auditlog/export.csv?" + qs() }, "Download as CSV")));
  };
  const go = () => { st.offset = 0; draw(); };
  [su, sa, sr, from, to].forEach(e => e.onchange = go); q.oninput = () => { clearTimeout(q.t); q.t = setTimeout(go, 350); };
  await draw();
  return h("div", {}, head("Audit trail", "Who changed what, and when. Every add, edit, delete, merge, export and sign-in problem is recorded and cannot be edited here."),
    h("div", { class: "bar noprint", style: "flex-wrap:wrap;gap:8px" }, q, su, sa, sr, h("label", { class: "hint" }, "From ", from), h("label", { class: "hint" }, "To ", to)), body);
}
