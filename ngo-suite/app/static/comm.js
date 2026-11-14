/* White-label branding page, follow-up board, donor timeline, send-messages page. */
"use strict";
Element.prototype.setKids = function (...k) { this.replaceChildren(...k.flat(Infinity).filter(x => x != null && x !== false)); return this; };
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

/* ---------------- branding & setup ---------------- */
async function viewBranding() {
  const s = (await get("/meta")).settings; META.settings = s;
  const f = {}, inp = (k, l, hint, el) => { f[k] = el; return h("div", {}, h("label", {}, l), el, hint ? h("div", { class: "hint" }, hint) : null); };
  const color = h("input", { type: "color", value: s.brand_color || "#0f5e63", style: "width:64px;height:38px;padding:2px" });
  const hex = h("input", { value: s.brand_color || "#0f5e63", style: "width:110px" });
  color.oninput = () => { hex.value = color.value; applyBrand({ color: color.value }); };
  hex.onchange = () => { if (/^#[0-9a-fA-F]{6}$/.test(hex.value)) { color.value = hex.value; applyBrand({ color: hex.value }); } };
  const presets = ["#0f5e63", "#1f4e8c", "#7a2e3a", "#2f6b3a", "#5a3d8a", "#8a4b0f", "#222b36"].map(c => h("button", { class: "btn sm", style: `background:${c};width:34px;height:34px;border-color:${c}`, "aria-label": c, onclick: () => { color.value = c; hex.value = c; applyBrand({ color: c }); } }));
  const preview = h("div", { style: "margin:8px 0" }), status = h("div", { class: "hint" });
  const drawLogo = () => preview.setKids(BRAND.logo ? h("div", {}, h("div", { style: "background:#fff;border:1px solid var(--line);padding:8px;display:inline-block;border-radius:8px" }, logoImg("", 70)), " ", h("button", { class: "btn sm danger", onclick: async () => { if (await must(() => del("/branding/logo"))) { applyBrand({ logo: "" }); META.settings.brand_logo_ver = ""; drawLogo(); refreshSide(); toast("Logo removed"); } } }, "Remove logo")) : h("div", { class: "hint" }, "No logo yet."));
  drawLogo();
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif", onchange: () => {
    const fl = file.files[0]; if (!fl) return; if (fl.size > 300000) return toast("Logo is too big. Keep it under 300 KB.", true);
    const rd = new FileReader(); rd.onload = async () => { const r = await must(() => post("/branding/logo", { data: String(rd.result) })); if (r) { applyBrand({ logo: "/api/public/logo?v=" + r.ver }); META.settings.brand_logo_ver = r.ver; drawLogo(); refreshSide(); toast("Logo saved"); } }; rd.readAsDataURL(fl); } });
  const save = async (done) => {
    const o = { brand_product: f.brand_product.value, login_note: f.login_note.value, brand_color: hex.value, org_name: f.org_name.value, org_tagline: f.org_tagline.value, org_head: f.org_head.value, org_address: f.org_address.value, org_phone: f.org_phone.value, org_email: f.org_email.value, org_reg: f.org_reg.value, org_upi: f.org_upi.value };
    if (done) o.setup_done = "Yes";
    if (await must(() => put("/settings", o))) { toast(done ? "Setup complete" : "Saved"); META = await get("/meta"); applyBrand({ product: META.settings.brand_product, color: META.settings.brand_color, note: META.settings.login_note }); refreshSide(); }
  };
  return h("div", {}, head("Branding & setup", "Make this software yours: your name, logo and colour show on the login page, menu, printed documents, emails and the Donate page."),
    h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, "Name and look"), h("div", { class: "inputgrid" },
      inp("brand_product", "Software name (shown instead of “NGO Suite”)", "", h("input", { value: s.brand_product || "", maxlength: 40 })),
      inp("login_note", "Line under the name on the login page", "", h("input", { value: s.login_note || "", maxlength: 160 }))),
      h("label", { style: "margin-top:10px" }, "Main colour"), h("div", { class: "bar" }, color, hex, ...presets), h("div", { class: "hint" }, "Menu and buttons use this colour. It must be dark enough for white text. You see the change at once; press Save to keep it."),
      h("label", { style: "margin-top:10px" }, "Logo (PNG, JPG, WEBP or GIF, under 300 KB; a wide logo on a white or transparent background works best)"), preview, file, status),
    h("div", { class: "card", style: "margin-bottom:14px" }, h("h2", {}, "Your organisation (printed on receipts and letters)"), h("div", { class: "inputgrid" },
      inp("org_name", "Organisation name", "", h("input", { value: s.org_name || "" })), inp("org_tagline", "Line under the name", "", h("input", { value: s.org_tagline || "" })), inp("org_head", "Secretary or head", "", h("input", { value: s.org_head || "" })),
      inp("org_address", "Address", "", h("input", { value: s.org_address || "" })), inp("org_phone", "Phone", "", h("input", { value: s.org_phone || "" })), inp("org_email", "Email", "", h("input", { value: s.org_email || "" })),
      inp("org_reg", "Registration nos, if any", "", h("input", { value: s.org_reg || "" })), inp("org_upi", "UPI ID (for QR codes and the Donate page)", "", h("input", { value: s.org_upi || "" })))),
    h("div", { class: "actions", style: "justify-content:flex-start" }, h("button", { class: "btn pri", onclick: () => save(false) }, "Save"),
      s.setup_done === "Yes" ? null : h("button", { class: "btn", onclick: () => save(true) }, "Save and mark setup complete")),
    h("p", { class: "hint" }, "Next: set up email under Settings, then switch on the automations you want. Registration numbers and sample users are demo values until you change them (see Users)."));
}

/* ---------------- donor timeline ---------------- */
async function showTimeline(id) {
  const t = await must(() => get(`/donors/${id}/timeline`)); if (!t) return;
  const col = { Gift: "green", Email: "blue", Call: "amber", Visit: "amber", WhatsApp: "green" };
  const body = h("div", {}, h("div", { class: "hint" }, [t.donor.code, t.donor.phone, t.donor.email].filter(Boolean).join(" · "), t.donor.next_followup ? " · next follow-up " + fd(t.donor.next_followup) : ""),
    h("div", { class: "actions", style: "justify-content:flex-start;margin:8px 0" }, can("interactions") ? h("button", { class: "btn pri", onclick: () => { close(); openForm("interactions", null, { donor_id: id, date: asofISO(), owner: USER.name, channel: "Call", direction: "Out" }); } }, "+ Log a contact") : null),
    t.events.length ? h("div", { style: "max-height:55vh;overflow:auto" }, ...t.events.map(e => h("div", { style: "display:flex;gap:10px;padding:8px 0;border-top:1px solid var(--line)" }, h("div", { style: "width:86px;flex:none" }, fd(e.date)),
      h("div", {}, h("span", { class: "badge b-" + (col[e.kind] || "grey") }, e.kind), " ", h("b", {}, e.title), e.detail ? h("div", { class: "hint" }, e.detail) : null)))) : h("div", { class: "empty" }, "Nothing recorded yet."));
  const close = modal("Timeline · " + t.donor.name, body, { wide: true });
}

/* ---------------- follow-up board ---------------- */
async function viewFollowups() {
  const wrap = h("div", {});
  async function draw() {
    const d = await get("/followups"), total = d.overdue.length + d.due_today.length + d.soon.length;
    const card = r => {
      const lc = r.last_contact, ph = String(r.phone || "").replace(/\D/g, ""), wa = ph.length >= 10 ? "https://wa.me/" + (ph.length === 10 ? "91" + ph : ph) : null;
      return h("div", { class: "card", style: "margin-bottom:8px" }, h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap" },
        h("div", {}, h("b", {}, r.name), " ", h("span", { class: "hint" }, r.code), h("div", { class: "hint" }, [r.phone, r.email].filter(Boolean).join(" · ")),
          h("div", { class: "hint" }, r.last_gift ? `Last gift ${fd(r.last_gift)} · total ${money(r.total)}` : "No gifts yet"),
          lc ? h("div", { class: "hint" }, `Last contact ${fd(lc.date)} (${lc.channel || ""}${lc.outcome ? ", " + lc.outcome : ""}): ${lc.summary}`) : h("div", { class: "hint" }, "Never contacted")),
        h("div", { style: "text-align:right" }, h("span", { class: "badge b-" + (r.when === "overdue" ? "red" : r.when === "today" ? "amber" : "grey") }, r.when === "overdue" ? `${-r.days} days late` : r.when === "today" ? "Today" : `in ${r.days} days`),
          h("div", { class: "hint" }, fd(r.next_followup)))),
        h("div", { class: "actions noprint", style: "justify-content:flex-start;margin-top:8px" },
          can("interactions") ? h("button", { class: "btn sm pri", onclick: () => openForm("interactions", null, { donor_id: r.id, date: d.today, owner: USER.name, channel: "Call", direction: "Out" }, draw) }, "Log contact") : null,
          wa ? h("a", { class: "btn sm", href: wa, target: "_blank", rel: "noopener" }, "WhatsApp") : null,
          r.phone ? h("a", { class: "btn sm", href: "tel:" + String(r.phone).replace(/[^\d+]/g, "") }, "Call") : null,
          h("button", { class: "btn sm", onclick: () => showTimeline(r.id) }, "Timeline"),
          can("donors") ? h("button", { class: "btn sm", onclick: async () => { if (await must(() => put(`/t/donors/${r.id}`, { next_followup: addDays(d.today, 7) }))) { toast("Moved a week"); draw(); } } }, "Snooze 7 days") : null,
          can("donors") ? h("button", { class: "btn sm", onclick: async () => { if (await must(() => put(`/t/donors/${r.id}`, { next_followup: "" }))) { toast("Cleared"); draw(); } } }, "No follow-up needed") : null));
    };
    const sec = (t, rows) => rows.length ? h("div", { style: "margin-bottom:14px" }, h("h2", {}, `${t} (${rows.length})`), ...rows.map(card)) : null;
    wrap.setKids(...[head("Follow-ups", "Everyone you promised to contact. Logging a contact with a new follow-up date moves them forward automatically."),
      total ? null : h("div", { class: "card" }, h("div", { class: "empty" }, "No follow-ups due in the next 7 days. ✔")), sec("Overdue", d.overdue), sec("Due today", d.due_today), sec("Next 7 days", d.soon)].filter(Boolean));
  }
  await draw(); return wrap;
}

/* ---------------- broadcast composer ---------------- */
const FIELDS = ["first_name", "name", "org", "contact", "upi"];
const smsInfo = t => { const uni = /[^\x00-\x7F]/.test(t), n = t.length, per = uni ? (n <= 70 ? 70 : 67) : (n <= 160 ? 160 : 153); return `${n} characters · about ${Math.max(1, Math.ceil(n / per))} SMS${uni ? " (non-English letters use more)" : ""}`; };
async function viewMessages() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Broadcast"), h("div", { class: "card" }, "Ask an administrator or the accounts officer."));
  const [seg, tpls] = await Promise.all([get("/campaign/segments"), get("/t/templates")]);
  const gw = seg.gateway, S = META.settings;
  let channel = gw.whatsapp ? "whatsapp" : gw.sms ? "sms" : "whatsapp", mode = "official", counts = { email: 0, whatsapp: 0, sms: 0 }, sample = [];
  const ready = ch => ch === "email" ? seg.email : !!gw[ch];
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const segSel = h("select", {}, ...seg.segments.map(s => h("option", { value: s.key }, s.label)));
  const param = h("input", { placeholder: "Amount in ₹, e.g. 10000", style: "display:none" });
  const citySel = h("select", { style: "display:none" }, ...seg.cities.map(c => h("option", { value: c }, c)));
  const grpSel = h("select", { style: "display:none" }, ...(seg.groups.length ? seg.groups : ["(no groups yet)"]).map(c => h("option", { value: c }, c)));
  const langSel = h("select", { style: "display:none" }, ...seg.languages.map(c => h("option", { value: c }, c)));
  const tplSel = h("select", {});
  const subjLabel = h("label", {}, "Subject");
  const name = h("input", { placeholder: "Name for your records, e.g. Diwali greeting 2026" }), subject = h("input", { placeholder: "Email subject" });
  const body = h("textarea", { rows: 7, placeholder: "Write your message…" });
  try { const pf = JSON.parse(sessionStorage.getItem("ngo_prefill") || "null"); if (pf) { body.value = pf.body || ""; name.value = pf.name || ""; subject.value = pf.name || ""; sessionStorage.removeItem("ngo_prefill"); } } catch (e) { /* ignore */ }
  const ptpl = h("input", { placeholder: "Approved template name (WhatsApp) or DLT template ID (SMS)" }), pvars = h("input", { placeholder: "Merge fields in order, e.g. first_name,org" });
  const when = h("input", { type: "datetime-local", style: "display:none" });
  let schedule = false;
  const aud = h("div", { class: "audbox", "aria-live": "polite" }), phone = h("div", { class: "phone" }), out = h("div", {}), notice = h("div", {});
  const chips = h("div", { class: "chips" }, ...FIELDS.map(f => h("button", { class: "chip", type: "button", onclick: () => { const a = body.selectionStart ?? body.value.length; body.setRangeText("{" + f + "}", a, body.selectionEnd ?? a, "end"); body.focus(); drawPhone(); } }, "{" + f + "}")));
  const val = () => segSel.value === "language" ? langSel.value : segSel.value === "city" ? citySel.value : segSel.value === "contacts_group" ? grpSel.value : param.value;
  const sampleVals = () => { const n = sample[0] || "Asha Rao"; return { name: n, first_name: n.split(" ")[0], org: S.org_name || "", upi: S.org_upi || "", contact: [S.org_phone, S.org_email].filter(Boolean).join(" · ") }; };
  const fill = t => Object.entries(sampleVals()).reduce((x, [k, v]) => x.split("{" + k + "}").join(v), t);
  function drawPhone() {
    const t = fill(body.value) || "Your message appears here as people will see it.";
    phone.setKids(h("div", { class: "phonehead" }, channel === "email" ? "Email preview" : channel === "sms" ? (S.sms_sender || "Your organisation") : (S.wa_display || S.org_name || "Your organisation")),
      h("div", { class: "bubble " + channel }, channel === "email" ? h("b", {}, fill(subject.value) || "(subject)") : null, channel === "email" ? h("br") : null, t, h("div", { class: "bt" }, "10:30")),
      channel === "sms" ? h("div", { class: "hint" }, smsInfo(t)) : null);
  }
  function drawTabs() {
    tabs.setKids(...[["whatsapp", "WhatsApp"], ["sms", "SMS"], ["email", "Email"]].map(([k, l]) => h("button", { class: "tab" + (channel === k ? " on" : ""), role: "tab", "aria-selected": channel === k, onclick: () => { channel = k; mode = "official"; changed(); } }, l, h("span", { class: "dotc " + (ready(k) ? "ok" : "off"), title: ready(k) ? "Connected" : "Not connected" }))));
    const tf = tpls.filter(t => t.channel === (channel === "email" ? "Email" : channel === "sms" ? "SMS" : "WhatsApp"));
    tplSel.setKids(h("option", { value: "" }, "Start from a template…"), ...tf.map(t => h("option", { value: t.id }, t.name)));
    subject.style.display = subjLabel.style.display = channel === "email" ? "" : "none";
    prov.style.display = channel === "email" ? "none" : "";
    const own = channel === "whatsapp" && !ready("whatsapp");
    notice.setKids(ready(channel) ? null : h("div", { class: "card warn" }, h("b", {}, channel === "email" ? "Email is not set up." : (channel === "whatsapp" ? "WhatsApp" : "SMS") + " is not connected to an official number yet."), " ",
      h("a", { href: "#/a/settings" }, "Connect it in Settings"), " (you need a provider account; the Settings page explains what to get).", own ? h("div", { class: "hint" }, "Until then you can still make a one-tap list that opens each chat in WhatsApp on your own phone.") : null));
    sendBtn.disabled = !ready(channel); sendBtn.textContent = schedule ? "Schedule" : "Send now"; ownBtn.style.display = channel === "whatsapp" ? "" : "none";
  }
  async function refresh() {
    const r = await must(() => post("/campaign/preview", { segment: segSel.value, param: val() })); if (!r) return;
    counts = r.counts; sample = r.sample;
    const n = counts[channel];
    aud.setKids(h("div", { class: "big" }, n), h("div", {}, h("b", {}, n === 1 ? "person will get this" : "people will get this"),
      h("div", { class: "hint" }, `Email ${counts.email} · WhatsApp ${counts.whatsapp} · SMS ${counts.sms}. People without a ${channel === "email" ? "valid email" : "valid phone number"}, or who have not agreed to ${channel === "email" ? "emails" : "WhatsApp/SMS"}, are left out.`),
      sample.length ? h("div", { class: "hint" }, "e.g. " + sample.join(", ")) : null));
    drawPhone();
  }
  function changed() { drawTabs(); refresh(); }
  const prov = h("div", {}, h("label", {}, "Provider template (needed for WhatsApp messages to people who have not messaged you in the last 24 hours, and for SMS in India)"), ptpl, h("label", {}, "Merge fields for the template's {{1}}, {{2}} …"), pvars);
  segSel.onchange = () => { segSel.value; param.style.display = segSel.value === "big" ? "" : "none"; citySel.style.display = segSel.value === "city" ? "" : "none"; grpSel.style.display = segSel.value === "contacts_group" ? "" : "none"; langSel.style.display = segSel.value === "language" ? "" : "none"; refresh(); };
  param.oninput = () => { clearTimeout(param.t); param.t = setTimeout(refresh, 400); }; citySel.onchange = grpSel.onchange = langSel.onchange = refresh;
  tplSel.onchange = () => { const t = tpls.find(x => String(x.id) === tplSel.value); if (t) { subject.value = t.subject || ""; body.value = t.body; ptpl.value = t.provider_template || ""; pvars.value = t.variables || ""; if (!name.value) name.value = t.name.replace(/^(WhatsApp|SMS): /, ""); drawPhone(); } };
  body.oninput = subject.oninput = drawPhone;
  const modeRadios = h("div", { class: "seg" }, ...[["now", "Send now"], ["later", "Schedule for later"]].map(([k, l]) => h("button", { class: "tab" + ((k === "later") === schedule ? " on" : ""), type: "button", onclick: e => { schedule = k === "later"; when.style.display = schedule ? "" : "none"; [...modeRadios.children].forEach(b => b.classList.toggle("on", b === e.target)); sendBtn.textContent = schedule ? "Schedule" : "Send now"; } }, l)));
  const payload = () => ({ name: name.value, subject: subject.value, body: body.value, segment: segSel.value, param: val(), channel, template: ptpl.value, variables: pvars.value, schedule_at: schedule ? when.value : "" });
  const sendBtn = h("button", { class: "btn pri big", onclick: () => {
    if (!name.value.trim() || !body.value.trim() || (channel === "email" && !subject.value.trim())) return toast("Fill in the name" + (channel === "email" ? ", subject" : "") + " and message", true);
    if (schedule && !when.value) return toast("Pick the date and time", true);
    const n = counts[channel], via = channel === "email" ? "email" : channel === "whatsapp" ? "WhatsApp" : "SMS";
    confirmBox(`${schedule ? "Schedule" : "Send"} this ${via} message to ${n} ${n === 1 ? "person" : "people"}${schedule ? " at " + when.value.replace("T", " ") : " now"}? It cannot be undone once sent.`, async () => {
      const r = await must(() => post("/campaign/send", payload())); if (!r) return;
      toast(r.scheduled ? "Scheduled" : `Sending to ${r.total} people…`); await loadHist(); showCampaign(r.id);
    }, schedule ? "Schedule" : "Send");
  } }, "Send now");
  const ownBtn = h("button", { class: "btn", onclick: async () => {
    if (!body.value.trim()) return toast("Write the message first", true);
    const r = await must(() => post("/campaign/whatsapp", { segment: segSel.value, param: val(), body: body.value })); if (!r) return;
    out.setKids(h("div", { class: "card" }, h("h2", {}, `On your own phone: ${r.list.length} people`), h("p", { class: "hint" }, "Press each button; WhatsApp opens with the message ready and you press send. This uses your own number, so keep it for small lists. Each tap is saved in the Contact log."),
      ...r.list.map(x => { const b = h("a", { class: "btn sm", href: x.link, target: "_blank", rel: "noopener", onclick: async () => { b.textContent = "Opened ✓"; if (x.kind === "donor") await must(() => post("/t/interactions", { date: asofISO(), donor_id: x.id, channel: "WhatsApp", direction: "Out", summary: (name.value || "Message") + " (WhatsApp)", owner: USER.name })); } }, "Open WhatsApp");
        return h("div", { class: "rowline" }, h("div", {}, h("b", {}, x.name), " ", h("span", { class: "hint" }, x.phone)), b); })));
  } }, "Use my own phone instead");
  const histBox = h("div", {});
  async function loadHist() {
    const rows = await get("/campaigns");
    histBox.setKids(rows.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["When", "Name", "Via", "To", "Sent", "Failed", "Status"].map(x => h("th", {}, x)))),
      h("tbody", {}, ...rows.map(r => h("tr", { class: "click", onclick: () => showCampaign(r.id) }, h("td", {}, r.ts.replace("T", " ").slice(0, 16)), h("td", {}, r.name), h("td", {}, r.channel), h("td", { class: "n" }, r.total), h("td", { class: "n" }, r.sent), h("td", { class: "n" }, r.failed), h("td", {}, cell(r.status, "badge")[0])))))) : h("div", { class: "empty" }, "Nothing sent yet."));
  }
  await loadHist(); drawTabs(); drawPhone(); refresh();
  return h("div", {}, head("Broadcast", "Send one message to many people: official WhatsApp, SMS or email. Everyone sent to is recorded."),
    h("div", { class: "composer" },
      h("div", {},
        h("div", { class: "card step" }, h("div", { class: "stepn" }, "1"), h("div", { class: "stepb" }, h("h2", {}, "How"), tabs, notice)),
        h("div", { class: "card step" }, h("div", { class: "stepn" }, "2"), h("div", { class: "stepb" }, h("h2", {}, "Who"), h("div", { class: "bar" }, segSel, param, citySel, grpSel, langSel), aud,
          h("div", { class: "hint" }, "Add people under ", h("a", { href: "#/t/contacts" }, "Contacts"), " (or import a CSV there). Mark who has agreed to WhatsApp/SMS on their record."))),
        h("div", { class: "card step" }, h("div", { class: "stepn" }, "3"), h("div", { class: "stepb" }, h("h2", {}, "What"), h("div", { class: "bar" }, tplSel, h("a", { href: "#/t/templates" }, "Edit templates")), name, subjLabel, subject,
          h("label", {}, "Message"), body, chips, prov,
          h("p", { class: "hint" }, "Emails end with a “reply STOP” line. WhatsApp and SMS text must match what your provider approved; add your own opt-out wording to the approved template."))),
        h("div", { class: "card step" }, h("div", { class: "stepn" }, "4"), h("div", { class: "stepb" }, h("h2", {}, "When"), modeRadios, when,
          h("div", { class: "actions", style: "justify-content:flex-start;margin-top:12px" }, sendBtn, ownBtn))), out),
      h("div", { class: "side2" }, h("div", { class: "card" }, h("div", { class: "hint", style: "margin-bottom:8px" }, "What people will see"), phone))),
    h("h2", { style: "margin-top:18px" }, "Earlier sends"), histBox);
}

async function showCampaign(id) {
  const box = h("div", {}); let timer;
  const close = modal("Broadcast", box, { wide: true }); const stop = () => clearInterval(timer);
  const origRemove = document.querySelector(".modal-bg"); if (origRemove) new MutationObserver(() => { if (!document.body.contains(origRemove)) stop(); }).observe(document.body, { childList: true });
  async function draw() {
    const r = await must(() => get("/campaign/" + id)); if (!r) return stop();
    const running = r.status === "Sending", sched = r.status === "Scheduled";
    if (!running) stop();
    box.setKids(h("div", { class: "hint" }, `${r.name} · ${r.channel} · ${r.ts.replace("T", " ").slice(0, 16)} · by ${r.user}`),
      h("div", { class: "cards", style: "margin:10px 0" }, kpi("Status", r.status + (sched ? " for " + r.schedule_at.replace("T", " ") : "")), kpi("To", r.total), kpi("Accepted by provider", r.sent), kpi("Failed", r.failed, "", r.failed ? "bad" : "")),
      h("div", { class: "card", style: "margin-bottom:10px;white-space:pre-wrap" }, r.body),
      h("div", { class: "actions", style: "justify-content:flex-start" }, r.failed && !running && !sched ? h("button", { class: "btn pri", onclick: async () => { if (await must(() => post(`/campaign/${id}/retry`))) { toast("Retrying failed messages…"); timer = setInterval(draw, 2500); draw(); } } }, `Retry ${r.failed} failed`) : null,
        running || sched ? h("button", { class: "btn danger", onclick: async () => { if (await must(() => post(`/campaign/${id}/cancel`))) { toast("Cancelled"); draw(); } } }, "Cancel") : null, h("button", { class: "btn", onclick: draw }, "Refresh")),
      h("p", { class: "hint" }, "“Accepted by provider” means the provider took the message. Delivery and read receipts are shown in your provider's dashboard."),
      r.messages.length ? h("div", { class: "tablewrap", style: "max-height:40vh" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Name", "To", "Result", "Detail"].map(x => h("th", {}, x)))), h("tbody", {}, ...r.messages.map(m => h("tr", {}, h("td", {}, m.name), h("td", {}, m.to_addr), h("td", {}, h("span", { class: "badge b-" + (m.status === "sent" ? "green" : "red") }, m.status)), h("td", { style: "white-space:normal" }, m.error || "")))))) : h("div", { class: "empty" }, sched ? "Will send at the scheduled time." : "No messages yet."));
    if (running && !timer) timer = setInterval(draw, 2500);
  }
  await draw();
}

/* ---------------- gateway help + test (inside Settings) ---------------- */
function gatewayHelp(save) {
  const ch = h("select", {}, h("option", { value: "whatsapp" }, "WhatsApp"), h("option", { value: "sms" }, "SMS")), to = h("input", { placeholder: "Your own number, e.g. 98290 61234", type: "tel" }), tp = h("input", { placeholder: "Template name or DLT ID (optional)" }), vv = h("input", { placeholder: "Merge fields, e.g. first_name,org" });
  return h("div", {}, h("details", { class: "card", style: "margin-top:10px" }, h("summary", {}, "What do I need from a provider?"),
    h("div", { class: "hint", style: "margin-top:8px;white-space:normal" },
      h("p", {}, h("b", {}, "WhatsApp from your official number: "), "WhatsApp does not let software send from the normal WhatsApp app. You need the WhatsApp Business Platform: a Meta business account, a phone number added to it, the number's “phone number ID” and an access token from Meta's developer dashboard. Messages to people who have not written to you in the last 24 hours must use a template that Meta has approved. Create templates in your Meta account, then enter the same template name and merge fields on a template here. Meta (or your reseller) charges per conversation."),
      h("p", {}, h("b", {}, "SMS: "), "In India, SMS needs DLT registration of your organisation, sender ID and each message template. With MSG91, put the DLT-approved template ID on the template here. Twilio and similar providers have their own rules."),
      h("p", {}, h("b", {}, "Other providers: "), "Choose Custom and fill in the address, headers and a JSON body. Use {to}, {message}, {template}, {p1}, {p2}…"),
      h("p", {}, "Only message people who agreed to it. Keys and tokens are stored in your database file, never shown again on this page. Back up and protect that file."))),
    h("div", { class: "bar", style: "margin-top:10px" }, h("b", {}, "Test:"), ch, to, tp, vv, h("button", { class: "btn", onclick: async () => {
      if (!(await save())) return;
      const r = await must(() => post("/gateway/test", { channel: ch.value, to: to.value, template: tp.value, variables: vv.value })); if (r) toast("Test message accepted by the provider");
    } }, "Save, then send a test")));
}
