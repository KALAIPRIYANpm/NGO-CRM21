// v14: official documents file attach, and the CSR proposal builder.
function docFileAction(r) {
  const input = h("input", { type: "file", accept: ".pdf,.jpg,.jpeg,.png,.docx,application/pdf,image/*", style: "display:none" });
  input.onchange = async () => {
    const f = input.files[0]; if (!f) return;
    if (f.size > 10e6) { toast("File is over 10 MB. Compress it and try again.", true); return; }
    try {
      const resp = await fetch(`/api/odocs/${r.id}/file?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f, credentials: "same-origin" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || "Upload failed");
      toast("File saved"); route();
    } catch (e) { toast(e.message, true); }
  };
  const bits = [h("button", { class: "btn sm", onclick: ev => { ev.stopPropagation(); input.click(); } }, r.has_file === "Y" ? "Replace file" : "Attach file"), input];
  if (r.has_file === "Y") {
    bits.push(h("a", { class: "btn sm", href: `/api/odocs/${r.id}/file`, target: "_blank", onclick: ev => ev.stopPropagation() }, "Open"));
    bits.push(h("button", { class: "btn sm", onclick: ev => { ev.stopPropagation(); confirmBox("Remove the attached file? The record stays.", async () => { if (await must(() => del(`/odocs/${r.id}/file`))) { toast("File removed"); route(); } }, "Remove"); } }, "Remove file"));
  }
  return bits;
}

async function viewProposal() {
  const projects = (await get("/t/projects")) || [];
  let pipe = [];
  try { pipe = (await get("/t/csr_pipeline")) || []; } catch (e) { /* programme role cannot read it */ }
  const proj = h("select", {}, ...projects.map(p => h("option", { value: p.id }, p.name)));
  const co = h("input", { type: "text", list: "co-list", placeholder: "Company name" });
  const dl = h("datalist", { id: "co-list" }, ...pipe.map(x => h("option", { value: x.company })));
  const ask = h("input", { type: "number", min: "0", placeholder: "Amount asked, in rupees" });
  const months = h("input", { type: "number", min: "1", max: "60", value: "12" });
  const clause = h("select", {}, ...[["ii", "Education, skills and livelihood (ii)"], ["i", "Hunger, health, sanitation, water (i)"], ["iii", "Women and inclusion (iii)"], ["iv", "Environment (iv)"], ["x", "Rural development (x)"]].map(([v, l]) => h("option", { value: v }, l)));
  const notes = h("textarea", { rows: 3, placeholder: "Anything extra to add at the end (optional)" });
  const go = () => {
    if (!proj.value) { toast("Add a project first", true); return; }
    const q = new URLSearchParams({ project_id: proj.value, company: co.value, ask: ask.value, months: months.value, clause: clause.value, notes: notes.value });
    window.open("/api/proposal?" + q.toString(), "_blank");
  };
  return h("div", {},
    h("div", { class: "top" }, h("h1", {}, "CSR proposal")),
    h("div", { class: "card" },
      h("p", { class: "hint" }, "Builds a draft proposal from your own records: activities, beneficiaries, results, budget, registrations and trustees. Yellow brackets mark what only you can write. Read it, fill the brackets, and have your CA and trustees check it. If the company has its own format, use that instead."),
      h("label", {}, "Project"), proj, h("label", {}, "Company"), co, dl,
      h("label", {}, "Amount asked"), ask, h("label", {}, "Months"), months,
      h("label", {}, "Schedule VII area"), clause, h("label", {}, "Extra notes"), notes,
      h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: go }, "Open the draft"))));
}

// Notification bell: what is coming up or overdue, for this person's role.
function bellButton() {
  const badge = h("span", { class: "badge b-grey", style: "margin-left:4px" }, "…");
  const b = h("button", { class: "btn sm", "aria-label": "Notifications", onclick: showBell }, "Alerts", badge);
  const load = async () => {
    try { const d = await get("/notifications"); badge.textContent = d.count; badge.className = "badge " + (d.red ? "b-red" : d.count ? "b-amber" : "b-grey"); b._d = d; } catch (e) { badge.textContent = ""; }
  };
  load(); return b;
}
async function showBell() {
  const d = await must(() => get("/notifications?days=14")); if (!d) return;
  let close;
  const groups = {}; d.items.forEach(i => (groups[i.kind] = groups[i.kind] || []).push(i));
  const when = i => !i.date ? "" : i.days < 0 ? `${-i.days} day${i.days === -1 ? "" : "s"} ago` : i.days === 0 ? "Today" : i.days === 1 ? "Tomorrow" : new Date(i.date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const body = d.items.length ? Object.keys(groups).map(k => h("div", { style: "margin-bottom:10px" }, h("b", {}, k),
    ...groups[k].map(i => h("div", { style: "display:flex;gap:8px;padding:4px 0;border-top:1px solid #e3e8ea" },
      h("span", { style: "width:78px;flex:none;font-weight:600;color:" + (i.level === "red" ? "#a32" : "#8a5a00") }, when(i)),
      h("a", { href: i.link, onclick: () => close() }, i.text))))) : [h("div", { class: "empty" }, "Nothing coming up in the next 14 days.")];
  close = modal("Coming up in 14 days, and overdue", h("div", { style: "max-height:60vh;overflow:auto" }, ...body, h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Close"))));
}


// Account menu: one tidy button instead of six small ones in the page header.
async function signOut() {
  try { await post("/logout"); } catch (e) { if (!window.OFFLINE) throw e; }
  if (typeof offlineForget === "function") offlineForget(); USER = null; window.OFFLINE = false; showLogin();
}
function accountMenu() {
  const label = USER.name === META.roles[USER.role] ? USER.name : USER.name;
  const pop = h("div", { class: "acct-pop", role: "menu", hidden: "" });
  const btn = h("button", { class: "btn sm acct-btn", "aria-haspopup": "menu", "aria-expanded": "false" }, label, h("span", { "aria-hidden": "true" }, " ▾"));
  const item = (t, f) => h("button", { class: "acct-item", role: "menuitem", onclick: () => { shut(); f(); } }, t);
  const shut = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); document.removeEventListener("click", away, true); document.removeEventListener("keydown", esc, true); };
  const away = e => { if (!wrap.contains(e.target)) shut(); };
  const esc = e => { if (e.key === "Escape") { shut(); btn.focus(); } };
  pop.append(h("div", { class: "acct-who" }, USER.name, h("div", { class: "hint" }, META.roles[USER.role])));
  if (typeof langPicker === "function") pop.append(h("div", { class: "acct-lang" }, langPicker()));
  if (!window.OFFLINE) pop.append(item("Change password", changePw));
  pop.append(item("Display", () => displayDialog()));
  if (!window.OFFLINE) pop.append(item("Security (two-step)", twoStepModal));
  pop.append(item("Sign out", signOut));
  const wrap = h("div", { class: "acct" }, btn, pop);
  btn.onclick = () => { if (pop.hidden) { pop.hidden = false; btn.setAttribute("aria-expanded", "true"); setTimeout(() => { document.addEventListener("click", away, true); document.addEventListener("keydown", esc, true); }); const f = pop.querySelector(".acct-item"); if (f) f.focus(); } else shut(); };
  return wrap;
}
