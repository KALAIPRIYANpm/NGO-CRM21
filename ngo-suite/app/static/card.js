"use strict";
(function () {
  const $ = id => document.getElementById(id);
  const el = (t, a, ...k) => { const e = document.createElement(t); for (const [x, v] of Object.entries(a || {})) { if (x === "class") e.className = v; else if (v != null && v !== false) e.setAttribute(x, v); } for (const c of k.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c))); return e; };
  const IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const tok = new URLSearchParams(location.search).get("t") || "";
  fetch("/api/public/card/" + encodeURIComponent(tok)).then(r => r.ok ? r.json() : Promise.reject()).then(d => {
    document.documentElement.style.setProperty("--brand", /^#[0-9a-fA-F]{6}$/.test(d.color) ? d.color : "#0f5e63"); document.title = d.headline + " · " + d.org;
    const m = $("c"); m.replaceChildren();
    m.append(el("div", { class: "top" }, d.logo ? el("img", { src: d.logo, alt: "" }) : null, el("div", { class: "org" }, d.org), el("h1", {}, d.headline), el("div", { class: "sub" }, d.project + (d.place ? " · " + d.place : "") + " · " + d.month_label)));
    const st = [[d.people, "people reached"], [d.activities, "activities"], [d.volunteers, "volunteer places"], [d.per_person != null ? "₹" + IN.format(d.per_person) : null, "spent per person"]].filter(x => x[0] != null && x[0] !== 0 && x[0] !== "0");
    if (d.people || d.activities) m.append(el("div", { class: "stats" }, ...st.map(([v, l]) => el("div", { class: "st" }, el("b", {}, typeof v === "number" ? IN.format(v) : v), el("span", {}, l)))));
    if (d.photo_ids.length) m.append(el("div", { class: "ph" + (d.photo_ids.length === 1 ? " one" : "") }, ...d.photo_ids.map(i => el("figure", {}, el("img", { src: `/api/public/card/${encodeURIComponent(tok)}/photo/${i}`, alt: d.captions[i] || "Photo from the field", loading: "lazy" }), d.captions[i] ? el("figcaption", {}, d.captions[i]) : null))));
    if (d.story) m.append(el("div", { class: "sec" }, el("h2", {}, "A moment from this month"), el("p", { style: "margin:0;white-space:pre-wrap" }, d.story)));
    const w = []; if (d.kinds.length) w.push(el("p", { style: "margin:0 0 6px" }, "What we did: " + d.kinds.join(", ") + "."));
    if (d.villages.length) w.push(el("p", { style: "margin:0 0 6px" }, "Where: " + d.villages.join(", ") + "."));
    if (d.spent) w.push(el("p", { style: "margin:0" }, "Spent this month: ₹" + IN.format(d.spent) + "."));
    if (w.length) m.append(el("div", { class: "sec" }, el("h2", {}, "This month"), w));
    const rs = d.results.filter(r => r.target > 0);
    if (rs.length) m.append(el("div", { class: "sec" }, el("h2", {}, "Progress so far"), ...rs.map(r => { const p = Math.max(0, Math.min(100, Math.round(100 * (r.achieved || 0) / r.target))); return el("div", {}, el("div", {}, `${r.result}: ${IN.format(r.achieved || 0)} of ${IN.format(r.target)} ${r.unit || ""}`), el("div", { class: "bar" }, el("i", { style: "width:" + p + "%" })));})));
    m.append(el("div", { class: "foot" }, "Figures come from " + d.org + "'s own records." + (d.contact ? " Questions? " + d.contact : ""), el("br"), "Photos are shown with the permission of the people in them."));
  }).catch(() => { $("c").replaceChildren(el("div", { class: "err" }, el("h2", {}, "This link is no longer available"), el("p", {}, "Please ask the organisation to send it again."))); });
})();
