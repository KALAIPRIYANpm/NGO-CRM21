/* Shared inbox for WhatsApp and SMS replies. */
"use strict";
const SEC = { color: "#fff" };
async function viewInbox() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Inbox"), h("div", { class: "card" }, "Ask an administrator or the accounts officer."));
  const people = await get("/inbox/assignees");
  const list = h("div", { class: "ib-list" }), pane = h("div", { class: "ib-pane" }, h("div", { class: "empty" }, "Choose a conversation."));
  const filter = h("select", {}, h("option", { value: "" }, "All"), h("option", { value: "Open" }, "Open"), h("option", { value: "Done" }, "Done"));
  let cur = null;
  const when = ts => { const d = new Date(ts); return isNaN(d) ? "" : (d.toDateString() === new Date().toDateString() ? d.toTimeString().slice(0, 5) : fd(ts.slice(0, 10))); };
  const pretty = p => "+" + p.replace(/^(\d{2})(\d{5})(\d+)$/, "$1 $2 $3");
  async function drawList() {
    const ts = await must(() => get("/inbox/threads" + (filter.value ? "?status=" + filter.value : ""))); if (!ts) return;
    list.setKids(...(ts.length ? ts.map(t => h("button", { class: "ib-item" + (cur && cur.phone === t.phone && cur.channel === t.channel ? " on" : ""), onclick: () => open(t.channel, t.phone) },
      h("div", { style: "display:flex;gap:6px;align-items:center" }, h("b", { style: "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, t.name || pretty(t.phone)), t.unread ? h("span", { class: "badge b-red" }, t.unread) : null, h("span", { class: "hint" }, when(t.last_ts))),
      h("div", { class: "hint", style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, (t.channel === "sms" ? "SMS · " : "WhatsApp · ") + (t.last_dir === "out" ? "You: " : "") + (t.last_text || ""), t.status === "Done" ? " · done" : "", t.optout ? " · STOP" : ""))) : [h("div", { class: "empty" }, "No replies yet. They appear here once your provider is connected (see Settings, Receiving replies).")]));
  }
  async function open(channel, phone) {
    const t = await must(() => get(`/inbox/thread?channel=${channel}&phone=${encodeURIComponent(phone)}`)); if (!t) return;
    cur = { channel, phone: t.phone }; drawList(); refreshBadge();
    const box = h("textarea", { rows: 2, placeholder: t.optout ? "This person replied STOP." : t.can_reply ? "Write a reply…" : "More than 24 hours since their last message: WhatsApp needs an approved template (use Broadcast).", disabled: t.optout || !t.can_reply });
    const send = async () => { if (!box.value.trim()) return; if (await must(() => post("/inbox/reply", { channel, phone: t.phone, text: box.value }))) { box.value = ""; open(channel, phone); } };
    box.addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); });
    const assign = h("select", { onchange: async () => { if (await must(() => put("/inbox/thread", { channel, phone: t.phone, assignee: assign.value }))) { toast("Assigned"); drawList(); } } }, h("option", { value: "" }, "Not assigned"), ...people.map(p => h("option", { value: p.username }, p.name || p.username))); assign.value = t.assignee || "";
    const who = t.people[0];
    const msgs = h("div", { class: "ib-msgs" }, ...t.messages.map(m => h("div", { class: "ib-b " + (m.direction === "in" ? "in" : "out") + (m.kind === "stop" ? " stop" : "") }, m.kind === "stop" ? h("b", {}, "STOP · ") : m.kind === "start" ? h("b", {}, "START · ") : null, m.text,
      h("div", { class: "bt" }, (m.direction === "out" ? (m.user || "") + " · " : "") + when(m.ts) + (m.delivery ? " · " + m.delivery : "") + (m.kind === "auto" ? " · automatic" : "")))));
    pane.setKids(h("div", { class: "ib-head" }, h("div", { style: "flex:1" }, h("b", {}, (who && who.name) || t.messages.find(m => m.name)?.name || pretty(t.phone)), h("div", { class: "hint" }, pretty(t.phone) + " · " + (channel === "sms" ? "SMS" : "WhatsApp") + (who ? " · " + who.kind : " · not in your records"))),
      who ? h("a", { class: "btn sm", href: who.kind === "donor" ? "#/t/donors" : "#/t/contacts" }, "Open record") : h("button", { class: "btn sm", onclick: async () => { const r = await must(() => post("/inbox/add-contact", { phone: t.phone, name: t.messages.find(m => m.name)?.name })); if (r) { toast("Saved as a contact (not OK for broadcasts)"); open(channel, phone); } } }, "Save as contact"),
      assign, h("button", { class: "btn sm", onclick: async () => { if (await must(() => put("/inbox/thread", { channel, phone: t.phone, status: t.status === "Done" ? "Open" : "Done" }))) { toast(t.status === "Done" ? "Reopened" : "Marked done"); open(channel, phone); } } }, t.status === "Done" ? "Reopen" : "Mark done")),
      t.optout ? h("div", { class: "qbar bad" }, "This person replied STOP. They are excluded from every broadcast until they send START.") : null, msgs, h("div", { class: "ib-reply" }, box, h("button", { class: "btn pri", disabled: t.optout || !t.can_reply, onclick: send }, "Send")), !t.optout && !t.can_reply ? h("div", { class: "hint" }, "WhatsApp only allows free replies for 24 hours after their message.") : null);
    msgs.scrollTop = msgs.scrollHeight;
  }
  filter.onchange = drawList; await drawList();
  clearInterval(window._ibTimer); window._ibTimer = setInterval(() => { if (location.hash !== "#/r/inbox") return clearInterval(window._ibTimer); drawList(); if (cur) get(`/inbox/thread?channel=${cur.channel}&phone=${encodeURIComponent(cur.phone)}`).then(t => { const m = $(".ib-msgs"); if (m && m.children.length !== t.messages.length) open(cur.channel, cur.phone); }).catch(() => {}); }, 20000);
  return h("div", {}, head("Inbox", "Replies from donors and contacts. A reply of STOP removes the person from every broadcast at once."), h("div", { class: "bar" }, h("label", {}, "Show"), filter), h("div", { class: "ib" }, list, pane));
}
async function refreshBadge() {
  if (!USER || !["admin", "accountant"].includes(USER.role)) return;
  try { const r = await get("/inbox/count"); const a = document.querySelector('.side a[data-h="#/r/inbox"]'); if (a && a.firstChild && a.firstChild.nodeType === 3) a.firstChild.nodeValue = "Inbox" + (r.unread ? " (" + r.unread + ")" : ""); } catch (e) { /* offline */ }
}
function inboxHelp() {
  const base = (META.settings.public_url || "https://your-address").replace(/\/$/, "");
  const tok = () => { const a = new Uint8Array(18); crypto.getRandomValues(a); return [...a].map(x => x.toString(16).padStart(2, "0")).join(""); };
  const row = (l, v) => h("div", { style: "margin:4px 0" }, h("b", {}, l + ": "), h("code", { style: "word-break:break-all" }, v));
  return h("details", { class: "card", style: "margin-top:10px" }, h("summary", {}, "How to receive replies"),
    h("div", { class: "hint", style: "margin-top:8px;white-space:normal;line-height:1.55" },
      h("p", {}, "Your provider must be able to reach this software on the internet, so first follow docs/HTTPS.md (Cloudflare Tunnel) and put that address in \"Public web address\". Then give your provider the address below. Nothing is stored unless the provider proves the message is genuine."),
      h("p", {}, h("b", {}, "WhatsApp (Meta Cloud API). "), "In the Meta app dashboard open WhatsApp > Configuration, paste the Callback URL and the Verify token, press Verify, then subscribe to the \"messages\" field. Paste the App Secret (App settings > Basic) into the field above."), row("Callback URL", base + "/api/hook/meta"),
      h("p", {}, h("b", {}, "Twilio (WhatsApp or SMS). "), "In the Twilio console set \"When a message comes in\" to this address with method POST. Your Twilio token above is used to check each call."), row("Webhook URL", base + "/api/hook/twilio"),
      h("p", {}, h("b", {}, "Any other provider (MSG91, Gupshup, etc.). "), "If it can POST a JSON or form message to a web address, use this and make sure it sends the sender number as from, mobile or sender, and the text as text, message or body. Field names differ between providers, so test with one message. Add ?channel=sms for SMS."), row("Webhook URL", base + "/api/hook/generic?token=<your token>"),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: e => { const i = document.querySelector('input[data-k="wa_verify_token"]'); if (i) { i.value = tok(); toast("Made a token. Save settings, then paste it into Meta."); } } }, "Make a verify token"),
        h("button", { class: "btn", onclick: () => { const i = document.querySelector('input[data-k="inbound_token"]'); if (i) { i.value = tok(); toast("Made a token. Save settings, then use it in the webhook address."); } } }, "Make a webhook token")),
      h("p", {}, "STOP, STOPALL, UNSUBSCRIBE, CANCEL, END and QUIT (the whole message, English) switch the person off for every broadcast. START turns them back on. Other languages and longer sentences are not recognised: those arrive in the inbox for a person to handle.")));
}
