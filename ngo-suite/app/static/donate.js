"use strict";
(async function () {
  const m = document.getElementById("m");
  const el = (t, a, ...k) => { const e = document.createElement(t); for (const [x, y] of Object.entries(a || {})) { if (x.startsWith("on")) e.addEventListener(x.slice(2), y); else if (y !== false && y != null) e.setAttribute(x, y); } k.flat().forEach(c => c != null && e.append(c.nodeType ? c : document.createTextNode(String(c)))); return e; };
  let info;
  try { info = await (await fetch("/api/public/donate-info")).json(); } catch (e) { m.replaceChildren(el("div", { class: "card" }, "Could not load. Please try again.")); return; }
  if (!info.enabled) { m.replaceChildren(el("div", { class: "card" }, "This page is not available right now.")); return; }
  document.title = "Donate to " + info.name;
  try { const b = await (await fetch("/api/public/brand")).json(); if (/^#[0-9a-fA-F]{6}$/.test(b.color)) document.documentElement.style.setProperty("--brand", b.color); if (b.logo) info.logo = b.logo; } catch (e) {}
  const f = {}; const inp = (k, l, a) => { f[k] = el(a && a.area ? "textarea" : "input", a && a.area ? { rows: 3 } : { ...(a || {}) }); return el("div", {}, el("label", {}, l), f[k]); };
  const msg = el("div", { id: "msg", "aria-live": "polite" });
  const amt = el("input", { type: "number", min: "1", inputmode: "numeric", placeholder: "Amount (optional)" });
  const qr = el("img", { src: "/api/public/upi.svg", alt: "UPI QR code" });
  const pay = el("a", { class: "btn", href: info.link }, "Pay with a UPI app");
  amt.addEventListener("input", () => { const v = Math.max(0, Math.floor(+amt.value || 0)); pay.setAttribute("href", info.link + (v ? "&am=" + v : "")); });
  f.website = el("input", { class: "hp", tabindex: "-1", autocomplete: "off", "aria-hidden": "true", name: "website" });
  let oc = { outcomes: [], intro: "" }; try { oc = await (await fetch("/api/public/outcomes")).json(); } catch (e) { /* optional */ }
  const picks = {}, total = el("div", { class: "sub" });
  const upd = () => { const t = oc.outcomes.reduce((a, o) => a + (picks[o.id] || 0) * o.unit_cost, 0); total.textContent = t ? "Your choice comes to \u20b9" + t.toLocaleString("en-IN") : ""; if (t) { amt.value = t; amt.dispatchEvent(new Event("input")); f.amount.value = t; f.message.value = "I chose: " + oc.outcomes.filter(o => picks[o.id]).map(o => picks[o.id] + " x " + o.title).join("; "); } };
  const outCard = oc.outcomes.length ? el("div", { class: "card" }, el("h2", {}, "Choose what your gift does"), el("div", { class: "sub" }, oc.intro),
    ...oc.outcomes.map(o => { const q = el("input", { type: "number", min: "0", max: "99", value: "0", style: "width:72px", "aria-label": "How many: " + o.title }); q.addEventListener("input", () => { picks[o.id] = Math.max(0, Math.floor(+q.value || 0)); upd(); });
      return el("div", { style: "display:flex;gap:10px;align-items:center;justify-content:space-between;margin:10px 0" }, el("div", {}, el("b", {}, o.title), el("div", { class: "sub" }, "\u20b9" + o.unit_cost.toLocaleString("en-IN") + (o.per && o.per !== "one-time" ? " per " + o.per : "") + (o.description ? " \u00b7 " + o.description : ""))), q); }), total) : null;
  m.replaceChildren(
    el("div", { class: "card" }, info.logo ? el("img", { src: info.logo, alt: "", style: "max-height:60px;max-width:100%;display:block;margin-bottom:8px" }) : null, el("h1", {}, info.name), el("div", { class: "sub" }, info.tagline), el("p", {}, info.message)),
    ...(outCard ? [outCard] : []),
    el("div", { class: "card qr" }, el("h2", {}, "Step 1: Pay"), qr, el("div", {}, el("b", {}, info.upi)), el("div", { class: "sub" }, "Scan with any UPI app, or on a phone:"), el("div", {}, amt), pay),
    el("div", { class: "card" }, el("h2", {}, "Step 2: Tell us who you are"), el("div", { class: "sub" }, "So we can send your receipt. Phone or email is enough."),
      inp("name", "Your name", { autocomplete: "name" }), inp("phone", "Phone", { type: "tel", autocomplete: "tel" }), inp("email", "Email", { type: "email", autocomplete: "email" }), inp("amount", "Amount you paid (₹)", { type: "number", min: "1" }), inp("message", "Message (optional)", { area: 1 }), f.website,
      el("button", { onclick: async () => {
        msg.className = ""; msg.textContent = "Sending…";
        try {
          const r = await fetch("/api/public/pledge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: f.name.value, phone: f.phone.value, email: f.email.value, amount: f.amount.value, message: f.message.value, website: f.website.value }) });
          const d = await r.json();
          if (!r.ok) { msg.className = "err"; msg.textContent = d.error || "Could not send"; return; }
          msg.className = "ok"; msg.textContent = "Thank you! We will confirm your gift and send a receipt."; ["name", "phone", "email", "amount", "message"].forEach(k => f[k].value = "");
        } catch (e) { msg.className = "err"; msg.textContent = "No network connection. Please try again."; }
      } }, "Send"), msg),
    el("div", { class: "sub", style: "text-align:center" }, [info.phone, info.email].filter(Boolean).join(" · "), el("br"), info.reg, info.transparency ? el("div", {}, el("a", { href: "/transparency.html", style: "color:var(--brand)" }, "How we use your money")) : null));
})();
