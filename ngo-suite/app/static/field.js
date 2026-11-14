/* NGO Suite field app: phone home screen, photo/video capture, offline upload queue, gallery, expense claims. */
"use strict";
Object.assign(BADGE, { Pending: "amber", Rejected: "red", Paid: "green", Approved: "blue" });

/* ---------------- offline job queue (IndexedDB holds the photos, videos and form data) ---------------- */
const JQ = (() => {
  let dbp = null, mem = new Map(), broken = false;
  const open = () => dbp || (dbp = new Promise((res, rej) => {
    try {
      const r = indexedDB.open("ngo_field", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("jobs", { keyPath: "id" });
      r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
    } catch (e) { rej(e); }
  }));
  const run = async (mode, fn) => {
    if (broken) return null;
    try {
      const db = await open();
      return await new Promise((res, rej) => { const t = db.transaction("jobs", mode); const rq = fn(t.objectStore("jobs")); t.oncomplete = () => res(rq && rq.result); t.onerror = t.onabort = () => rej(t.error); });
    } catch (e) { broken = true; return null; }
  };
  return {
    get broken() { return broken; },
    async put(j) { const r = await run("readwrite", s => s.put(j)); if (broken) mem.set(j.id, j); return r; },
    async all() { const r = await run("readonly", s => s.getAll()); return broken ? [...mem.values()] : (r || []); },
    async del(id) { mem.delete(id); return run("readwrite", s => s.delete(id)); },
  };
})();

function xhrPost(path, blob, onp) {
  return new Promise(resolve => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api" + path); x.timeout = 15 * 60 * 1000;
    x.setRequestHeader("Content-Type", blob.type || "application/octet-stream");
    if (onp) x.upload.onprogress = e => { if (e.lengthComputable) onp(e.loaded / e.total); };
    x.onload = () => { let d = null; try { d = JSON.parse(x.responseText); } catch (e) { /* not json */ } resolve({ status: x.status, data: d }); };
    x.onerror = x.ontimeout = x.onabort = () => resolve({ status: 0 });
    x.send(blob);
  });
}
async function jsonPost(path, body) {
  try { return { status: 200, data: await api("POST", path, body) }; }
  catch (e) { return { status: e.status === undefined ? 0 : e.status, error: e.message }; }
}

/* Runs one waiting job. Safe to repeat: the server remembers each client_id, so a lost reply never makes a duplicate. */
async function runJob(job, onp) {
  const bad = (r, what) => {
    if (r.status === 0 || r.status >= 500) return "retry";
    if (r.status === 401) { job.error = "You were signed out. Sign in, then press Upload now."; return "auth"; }
    job.error = (r.error || (r.data && r.data.error) || "Refused") + (what ? " (" + what + ")" : ""); return "failed";
  };
  job.error = "";
  if (!job.recordId) {
    const r = await jsonPost(job.type === "activity" ? "/field/activity" : "/claims", { ...job.body, client_id: job.id });
    if (r.status !== 200) { const o = bad(r); await JQ.put(job); return o; }
    job.recordId = r.data.id; await JQ.put(job);
  }
  for (let i = 0; i < job.items.length; i++) {
    const it = job.items[i];
    if (!it.mediaId) {
      const q = new URLSearchParams({ kind: it.kind, consent: it.consent ? "Y" : "N", caption: it.caption || "", taken_at: it.taken_at || "", client_id: job.id + "-" + i });
      if (job.type === "activity") { q.set("activity_id", job.recordId); if (job.body.project_id) q.set("project_id", job.body.project_id); } else q.set("claim_id", job.recordId);
      const r = await xhrPost("/media?" + q, it.blob, p => onp && onp((i + p) / job.items.length));
      if (r.status !== 200) { const o = bad(r, it.kind); await JQ.put(job); return o; }
      it.mediaId = r.data.id; await JQ.put(job);
    }
    if (it.thumb && !it.thumbDone) {
      const r = await xhrPost(`/media/${it.mediaId}/thumb`, it.thumb);
      if (r.status === 0 || r.status >= 500) return "retry";
      it.thumbDone = true; await JQ.put(job);
    }
  }
  await JQ.del(job.id); return "done";
}
async function flushJobs(onp) {
  if (flushJobs.busy) return { done: 0, left: 0, failed: 0, busy: true };
  flushJobs.busy = true;
  let done = 0, left = 0, failed = 0;
  try {
    for (const job of (await JQ.all()).filter(j => j.user === USER.id).sort((a, b) => a.created < b.created ? -1 : 1)) {
      if (job.error && !flushJobs.retryFailed) { failed++; continue; }
      const o = await runJob(job, onp);
      if (o === "done") done++; else if (o === "failed") failed++; else { left++; if (o === "auth") break; }
    }
  } finally { flushJobs.busy = false; flushJobs.retryFailed = false; }
  if (done) toast(done + " item(s) uploaded");
  if (window._qrefresh) window._qrefresh();
  return { done, left, failed };
}
const newJobId = () => "j" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
async function queueJob(type, body, items, label) {
  const job = { id: newJobId(), user: USER.id, type, body, label, created: new Date().toISOString(), items: items.map(i => ({ kind: i.kind, blob: i.blob, thumb: i.thumb, consent: i.consent, taken_at: i.taken_at })), recordId: null, error: "" };
  await JQ.put(job);
  if (JQ.broken) toast("This phone cannot keep unsent items. Stay online until the upload finishes.", true);
  return job;
}
if (!window._fieldBg) {
  window._fieldBg = true;
  window.addEventListener("online", () => { if (USER) flushJobs(); });
  setInterval(() => { if (USER && navigator.onLine) JQ.all().then(a => { if (a.some(j => j.user === USER.id && !j.error)) flushJobs(); }); }, 60000);
  window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); window._installEv = e; });
  if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => { /* needs https or localhost */ }));
}

/* ---------------- photo and video processing on the phone ---------------- */
async function shrinkPhoto(file, max, q) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const cv = document.createElement("canvas"); cv.width = Math.max(1, Math.round(img.naturalWidth * k)); cv.height = Math.max(1, Math.round(img.naturalHeight * k));
    cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
    return await new Promise((res, rej) => cv.toBlob(b => b ? res(b) : rej(new Error("encode")), "image/jpeg", q));
  } finally { URL.revokeObjectURL(url); }
}
function videoThumb(file) {
  return new Promise(res => {
    const url = URL.createObjectURL(file), v = document.createElement("video"); let done = false;
    v.muted = true; v.playsInline = true; v.preload = "metadata";
    const fin = b => { if (done) return; done = true; URL.revokeObjectURL(url); res(b); };
    setTimeout(() => fin(null), 6000);
    v.onloadeddata = () => { try { v.currentTime = Math.min(0.5, (v.duration || 1) / 2); } catch (e) { fin(null); } };
    v.onseeked = () => { try { const k = Math.min(1, 320 / Math.max(v.videoWidth || 320, v.videoHeight || 240)); const cv = document.createElement("canvas"); cv.width = Math.round(v.videoWidth * k) || 320; cv.height = Math.round(v.videoHeight * k) || 180; cv.getContext("2d").drawImage(v, 0, 0, cv.width, cv.height); cv.toBlob(b => fin(b), "image/jpeg", .7); } catch (e) { fin(null); } };
    v.onerror = () => fin(null); v.src = url;
  });
}
const MAX_VIDEO_MB = 60;

/* Capture widget: take photo, record video, or pick from the phone. kind: "event" (photos + video + consent) or "bill" (photos only). */
function captureBox(kind) {
  const items = [];
  const grid = h("div", { class: "shots" }), status = h("div", { class: "hint", "aria-live": "polite" });
  const consent = h("input", { type: "checkbox", id: "consent" + Math.random().toString(36).slice(2, 6) });
  const mk = (accept, capture, multiple) => { const i = h("input", { type: "file", accept, multiple: !!multiple, style: "display:none" }); if (capture) i.setAttribute("capture", "environment"); i.onchange = () => { add([...i.files]); i.value = ""; }; return i; };
  const camPhoto = mk("image/*", true), camVideo = mk("video/*", true), pick = mk(kind === "bill" ? "image/*" : "image/*,video/*", false, true);
  const draw = () => {
    grid.replaceChildren(...items.map((it, n) => h("div", { class: "shot" },
      it.kind === "photo" ? h("img", { src: it.url, alt: "Photo " + (n + 1) }) : (it.thumbUrl ? h("img", { src: it.thumbUrl, alt: "Video " + (n + 1) }) : h("div", { style: "color:#fff;padding:10px;font-size:13px" }, "Video")),
      it.kind === "video" ? h("span", { class: "tag" }, "Video " + Math.round(it.blob.size / 1e5) / 10 + " MB") : null,
      h("button", { class: "x", type: "button", "aria-label": "Remove", onclick: () => { URL.revokeObjectURL(it.url); if (it.thumbUrl) URL.revokeObjectURL(it.thumbUrl); items.splice(n, 1); draw(); } }, "×"))));
    status.textContent = items.length ? items.length + " attached" : "";
  };
  async function add(files) {
    for (const f of files) {
      status.textContent = "Preparing…";
      try {
        if (f.type.startsWith("video/") || /\.(mp4|mov|webm)$/i.test(f.name)) {
          if (kind === "bill") { toast("Bills must be photos", true); continue; }
          if (f.size > MAX_VIDEO_MB * 1e6) { toast(`That video is ${Math.round(f.size / 1e6)} MB. The limit is ${MAX_VIDEO_MB} MB. Record at 720p or a shorter clip.`, true); continue; }
          const th = await videoThumb(f);
          items.push({ kind: "video", blob: f, thumb: th, url: URL.createObjectURL(f), thumbUrl: th ? URL.createObjectURL(th) : null, taken_at: new Date(f.lastModified || Date.now()).toISOString().slice(0, 19) });
        } else if (f.type.startsWith("image/") || /\.(jpe?g|png|webp|heic)$/i.test(f.name)) {
          let b;
          try { b = await shrinkPhoto(f, 1600, .8); }
          catch (e) { if (/^image\/(jpeg|png|webp)$/.test(f.type) && f.size <= 8e6) b = f; else { toast("This photo format cannot be read here. Take a new photo instead.", true); continue; } }
          const th = await shrinkPhoto(b, 320, .7).catch(() => null);
          items.push({ kind: "photo", blob: b, thumb: th, url: URL.createObjectURL(b), taken_at: new Date(f.lastModified || Date.now()).toISOString().slice(0, 19) });
        } else toast("Unsupported file: " + f.name, true);
      } catch (e) { toast("Could not prepare " + f.name, true); }
    }
    draw();
  }
  const btn = (l, input) => h("button", { class: "btn", type: "button", onclick: () => input.click() }, l);
  const el = h("div", {}, h("div", { class: "capbtns" }, btn(kind === "bill" ? "Photograph the bill" : "Take photo", camPhoto), kind === "bill" ? null : btn("Record video", camVideo), btn("Choose from phone", pick)), camPhoto, camVideo, pick, grid, status,
    kind === "bill" ? null : h("label", { class: "consent", for: consent.id }, consent, h("span", {}, h("b", {}, "Everyone shown agreed to be photographed. "), h("span", { class: "hint" }, "Tick only if you have their permission (a parent or guardian for children). Without this, the photos stay internal and view-only staff cannot see them."))));
  return { el, items, get consent() { return consent.checked; }, clear() { items.forEach(i => { URL.revokeObjectURL(i.url); if (i.thumbUrl) URL.revokeObjectURL(i.thumbUrl); }); items.length = 0; consent.checked = false; draw(); } };
}
const readyItems = cap => cap.items.map(i => ({ ...i, consent: cap.consent }));

/* ---------------- upload queue panel ---------------- */
function queuePanel() {
  const box = h("div", {});
  const draw = async () => {
    const all = await JQ.all(), mine = all.filter(j => j.user === USER.id), other = all.length - mine.length;
    const legacy = (typeof qGet === "function" ? qGet() : []).length;
    if (!mine.length && !other && !legacy) { box.replaceChildren(h("div", { class: "qbar" }, "Everything is saved on the server.")); return; }
    const rows = mine.map(j => h("div", { class: "qbar" + (j.error ? " bad" : " warn") },
      h("div", { style: "flex:1;min-width:180px" }, h("b", {}, j.label || j.type), h("div", { class: "hint" }, (j.items.length ? j.items.length + " photo/video · " : "") + (j.error ? j.error : (j.recordId ? "details sent, files uploading" : "waiting to upload")))),
      j.error ? h("button", { class: "btn", onclick: async () => { j.error = ""; await JQ.put(j); flushJobs.retryFailed = true; await flushJobs(); draw(); } }, "Retry") : null,
      j.error ? h("button", { class: "btn", onclick: () => confirmBox("Discard this waiting item? Its photos and details on this phone will be lost.", async () => { await JQ.del(j.id); draw(); }, "Discard") }, "Discard") : null));
    const total = h("div", { class: "qbar warn" }, h("b", {}, (mine.length + legacy) + " item(s) waiting on this phone."), h("span", { class: "grow" }),
      h("button", { class: "btn pri", onclick: async () => { if (!navigator.onLine) toast("No network yet", true); flushJobs.retryFailed = true; if (typeof flushQueue === "function") await flushQueue(); await flushJobs(); draw(); } }, "Upload now"));
    box.replaceChildren(total, ...rows, ...(other ? [h("div", { class: "hint" }, other + " waiting item(s) belong to another user of this phone. They upload when that person signs in.")] : []));
  };
  window._qrefresh = draw; draw(); return box;
}
function progressBar() { const i = h("i", {}), el = h("div", { class: "prog", style: "display:none", role: "progressbar" }, i); return { el, set(p) { el.style.display = p == null ? "none" : ""; i.style.width = Math.round((p || 0) * 100) + "%"; } }; }
const roleOk = () => USER && ["admin", "programme"].includes(USER.role);
const noAccess = t => h("div", {}, head(t), h("div", { class: "card" }, "Your role cannot use this page. Ask an administrator if you need field access."));
const select = (opts, blank) => h("select", {}, blank === null ? null : h("option", { value: "" }, blank || "Choose…"), ...opts.map(o => h("option", { value: o.value ?? o }, o.label ?? o)));
const field = (l, el) => h("div", {}, h("label", {}, l), el);

/* ---------------- field home ---------------- */
async function viewFieldHome() {
  const w = h("div", { class: "fieldbig" });
  const tiles = [];
  if (roleOk()) tiles.push(h("a", { class: "tile pri", href: "#/r/fieldact" }, h("b", {}, "Log an activity"), h("span", {}, "Event, camp or visit, with photos and video")),
    h("a", { class: "tile", href: "#/r/fieldpeople" }, h("b", {}, "Attendance and new people"), h("span", {}, "Mark the team, add a person served")),
    h("a", { class: "tile", href: "#/r/fieldclaim" }, h("b", {}, "Expense claim"), h("span", {}, "Photograph the bill, send for approval")));
  tiles.push(h("a", { class: "tile", href: "#/r/gallery" }, h("b", {}, "Photos and videos"), h("span", {}, "Gallery of events")));
  if (USER.role !== "viewer") tiles.push(h("a", { class: "tile", href: "#/r/claims" }, h("b", {}, "Claims"), h("span", {}, USER.role === "programme" ? "Status of my claims" : "Approve and pay")));
  const inst = h("div", {});
  if (window._installEv) inst.append(h("button", { class: "btn pri", onclick: async () => { window._installEv.prompt(); window._installEv = null; inst.replaceChildren(); } }, "Install this app on the phone"));
  else if (/iPhone|iPad/.test(navigator.userAgent) && !navigator.standalone) inst.append(h("div", { class: "hint" }, "To install on iPhone: tap the Share button, then Add to Home Screen."));
  w.append(head("Field app", "Everything for the field in one place. Works with weak or no network: entries wait on this phone and upload later.", langPicker()), h("div", { class: "tiles" }, ...tiles), inst, h("h2", { style: "margin-top:16px" }, "Waiting to upload"), queuePanel());
  flushJobs();
  return w;
}

/* ---------------- log an activity with photos and videos ---------------- */
async function viewFieldAct() {
  if (!roleOk()) return noAccess("Log an activity");
  const proj = await projectOptions();
  const cap = captureBox("event"), pb = progressBar();
  const f = {
    date: h("input", { type: "date", value: asofISO() }), project_id: select(proj.map(p => ({ value: p.id, label: p.label || p.name }))), activity: select(META.lists.activity || []), village: select(META.lists.village || []),
    people_reached: h("input", { type: "number", inputmode: "numeric", min: 0 }), volunteers: h("input", { type: "number", inputmode: "numeric", min: 0 }), spent: h("input", { type: "number", inputmode: "decimal", min: 0 }), note: h("textarea", { rows: 3 }),
  };
  const save = h("button", { class: "btn pri", style: "width:100%;margin-top:10px", onclick: async () => {
    if (!f.project_id.value) return toast("Choose the project", true);
    if (!f.date.value) return toast("Choose the date", true);
    save.disabled = true;
    const body = {}; for (const k of Object.keys(f)) body[k] = f[k].value;
    const items = readyItems(cap);
    const p = proj.find(x => String(x.id) === f.project_id.value);
    const job = await queueJob("activity", body, items, (f.activity.value || "Activity") + " · " + ((p && (p.label || p.name)) || "") + (items.length ? "" : ""));
    pb.set(0);
    const r = await flushJobs(x => pb.set(x));
    pb.set(null); save.disabled = false;
    const left = (await JQ.all()).find(j => j.id === job.id);
    if (!left) { toast("Saved" + (items.length ? " with " + items.length + " file(s)" : "")); cap.clear(); Object.values(f).forEach(e => { if (e !== f.date) e.value = ""; }); }
    else toast(left.error ? "Not saved: " + left.error : "Saved on this phone. It uploads when the network is back.", !!left.error);
    window._qrefresh && window._qrefresh();
  } }, "Save activity");
  return h("div", { class: "fieldbig" }, head("Log an activity", "What happened today, with photos or video as proof."),
    h("div", { class: "card" }, h("div", { class: "inputgrid" }, field("Project", f.project_id), field("Date", f.date), field("Activity", f.activity), field("Village or ward", f.village),
      field("People reached", f.people_reached), field("Volunteers", f.volunteers), field("Spent (₹)", f.spent), field("Note", f.note))),
    h("div", { class: "card", style: "margin-top:12px" }, h("h2", {}, "Photos and video"), cap.el), pb.el, save, h("h2", { style: "margin-top:16px" }, "Waiting to upload"), queuePanel());
}

/* ---------------- expense claim with bill photo ---------------- */
async function viewFieldClaim() {
  if (!roleOk()) return noAccess("Expense claim");
  const proj = await projectOptions();
  const cap = captureBox("bill"), pb = progressBar();
  const f = { date: h("input", { type: "date", value: asofISO() }), project_id: select(proj.map(p => ({ value: p.id, label: p.label || p.name })), "No project"), category: select(META.lists.claim_category || ["Other"], null),
    amount: h("input", { type: "number", inputmode: "decimal", min: 0, step: "0.01" }), description: h("textarea", { rows: 3, placeholder: "What was it for?" }) };
  const nobill = h("input", { type: "checkbox" });
  const save = h("button", { class: "btn pri", style: "width:100%;margin-top:10px", onclick: async () => {
    if (!(+f.amount.value > 0)) return toast("Enter the amount", true);
    if (!cap.items.length && !nobill.checked) return toast("Photograph the bill, or tick 'No bill available' and explain in the description", true);
    if (nobill.checked && !f.description.value.trim()) return toast("Explain why there is no bill", true);
    save.disabled = true;
    const body = {}; for (const k of Object.keys(f)) body[k] = f[k].value;
    const job = await queueJob("claim", body, readyItems(cap).map(i => ({ ...i, consent: false })), "Claim ₹" + f.amount.value + " · " + f.category.value);
    pb.set(0); await flushJobs(x => pb.set(x)); pb.set(null); save.disabled = false;
    const left = (await JQ.all()).find(j => j.id === job.id);
    if (!left) { toast("Claim sent for approval"); cap.clear(); f.amount.value = ""; f.description.value = ""; nobill.checked = false; }
    else toast(left.error ? "Not sent: " + left.error : "Saved on this phone. It is sent when the network is back.", !!left.error);
    window._qrefresh && window._qrefresh();
  } }, "Send for approval");
  return h("div", { class: "fieldbig" }, head("Expense claim", "Money you spent for the work. Finance approves it and pays you back."),
    h("div", { class: "card" }, h("div", { class: "inputgrid" }, field("Amount (₹)", f.amount), field("Category", f.category), field("Date of expense", f.date), field("Project", f.project_id), field("Description", f.description))),
    h("div", { class: "card", style: "margin-top:12px" }, h("h2", {}, "Bill"), cap.el, h("label", { class: "consent" }, nobill, h("span", {}, "No bill available (explain in the description)"))), pb.el, save,
    h("div", { class: "hint", style: "margin:6px 2px" }, "Bills are visible only to you and to finance."), h("h2", { style: "margin-top:16px" }, "Waiting to upload"), queuePanel());
}

/* ---------------- gallery ---------------- */
async function viewGallery() {
  const proj = await get("/options/projects");
  const grid = h("div", { class: "gal" }), more = h("div", { class: "actions" }), out = h("div", {});
  const fp = select(proj.map(p => ({ value: p.id, label: p.label || p.name })), "All projects"), fk = select([{ value: "photo", label: "Photos" }, { value: "video", label: "Videos" }], "Photos and videos");
  const fc = USER.role === "viewer" ? null : select([{ value: "Y", label: "Consent given" }, { value: "N", label: "Consent not confirmed" }], "Any consent");
  let last = null;
  const card = m => {
    const pic = h("img", { src: `/api/media/${m.id}/thumb`, loading: "lazy", alt: m.caption || (m.kind === "video" ? "Video" : "Photo"), onerror: e => e.target.replaceWith(h("div", { style: "color:#fff;padding:10px;font-size:13px" }, m.kind === "video" ? "Video" : "Photo")) });
    return h("div", { class: "shot", tabindex: 0, role: "button", "aria-label": (m.caption || m.project || "Open") + (m.kind === "video" ? " (video)" : ""), onclick: () => open(m), onkeydown: e => { if (e.key === "Enter") open(m); } }, pic,
      m.kind === "video" ? h("span", { class: "tag" }, "Video") : null, m.consent !== "Y" && USER.role !== "viewer" ? h("span", { class: "tag no", style: "left:auto;right:4px;bottom:4px" }, "No consent") : null);
  };
  const load = async reset => {
    if (reset) { grid.replaceChildren(); last = null; }
    const q = new URLSearchParams({ limit: 36 }); if (fp.value) q.set("project_id", fp.value); if (fk.value) q.set("kind", fk.value); if (fc && fc.value) q.set("consent", fc.value); if (last) q.set("before", last);
    const r = await must(() => get("/media?" + q)); if (!r) return;
    r.items.forEach(m => grid.append(card(m))); if (r.items.length) last = r.items[r.items.length - 1].id;
    more.replaceChildren(...(r.more ? [h("button", { class: "btn", onclick: () => load(false) }, "Show more")] : []));
    out.replaceChildren(grid.children.length ? "" : h("div", { class: "empty" }, "Nothing here yet. Photos and videos logged from the field app appear here."));
  };
  const open = m => {
    const mine = m.uploaded_by === USER.id || USER.role === "admin";
    const media = m.kind === "video" ? h("video", { controls: true, playsinline: true, preload: "metadata", src: `/api/media/${m.id}/file`, poster: m.has_thumb ? `/api/media/${m.id}/thumb` : null }) : h("img", { src: `/api/media/${m.id}/file`, alt: m.caption || "Photo" });
    const cap = h("input", { value: m.caption || "", maxlength: 300 }), cons = select([{ value: "Y", label: "Consent given" }, { value: "N", label: "Consent not confirmed" }], null); cons.value = m.consent;
    const close = modal((m.kind === "video" ? "Video" : "Photo") + (m.project ? " · " + m.project : ""), h("div", { class: "lightbox" }, media,
      h("div", { class: "hint", style: "margin:8px 0" }, `${m.uploader || ""} · ${fd((m.taken_at || m.created || "").slice(0, 10))}`),
      mine ? h("div", { class: "inputgrid" }, field("Caption", cap), field("Consent", cons)) : (m.caption ? h("div", {}, m.caption) : null),
      h("div", { class: "actions" }, h("a", { class: "btn", href: `/api/media/${m.id}/file`, download: "" }, "Download"),
        mine ? h("button", { class: "btn", onclick: async () => { if (await must(() => put("/media/" + m.id, { caption: cap.value, consent: cons.value }))) { toast("Saved"); close(); load(true); } } }, "Save changes") : null,
        mine ? h("button", { class: "btn", style: "color:var(--red)", onclick: () => confirmBox("Delete this " + m.kind + " for good?", async () => { if (await must(() => del("/media/" + m.id))) { close(); toast("Deleted"); load(true); } }) }, "Delete") : null,
        h("button", { class: "btn", onclick: () => close() }, "Close"))), { wide: true });
  };
  [fp, fk, fc].forEach(x => x && (x.onchange = () => load(true)));
  await load(true);
  return h("div", {}, head("Photos and videos", USER.role === "viewer" ? "Only items where everyone shown has agreed are listed." : "Event photos and videos from the field."), h("div", { class: "bar" }, fp, fk, fc,
    h("span", { class: "grow" }), roleOk() ? h("a", { class: "btn pri", href: "#/r/fieldact" }, "Add from field app") : null), out, grid, more);
}

/* ---------------- claims: status for staff, approve and pay for finance ---------------- */
async function viewClaims() {
  if (USER.role === "viewer") return noAccess("Claims");
  const fin = ["admin", "accountant"].includes(USER.role);
  const out = h("div", {}), fs = select(["Pending", "Approved", "Paid", "Rejected"], "All statuses");
  const bills = async c => {
    const r = await must(() => get(`/media?purpose=bill&claim_id=${c.id}`)); if (!r) return;
    modal("Bill for " + c.claim_no, h("div", {}, ...(r.items.length ? r.items.map(m => h("img", { src: `/api/media/${m.id}/file`, alt: "Bill", style: "max-width:100%;border-radius:8px;margin-bottom:8px;display:block" })) : [h("div", { class: "empty" }, "No bill photo attached.")])), { wide: true });
  };
  const decide = (c, act) => {
    const remark = h("input", { placeholder: act === "reject" ? "Reason (required)" : "Note (optional)" });
    const close = modal((act === "approve" ? "Approve " : "Reject ") + c.claim_no + " · " + money(c.amount), h("div", {}, field("Remark", remark), h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"),
      h("button", { class: "btn pri", onclick: async () => { if (await must(() => post(`/claims/${c.id}/review`, { action: act, remark: remark.value }))) { close(); toast("Done"); draw(); } } }, act === "approve" ? "Approve" : "Reject"))));
  };
  const pay = async c => {
    const funds = await get("/options/funds"), fund = select(funds.map(x => ({ value: x.id, label: x.label || x.name })), "Choose fund"), mode = select(META.lists.mode || ["Cash"], null), day = h("input", { type: "date", value: asofISO() });
    const close = modal("Pay " + c.claim_no + " · " + money(c.amount) + " to " + c.claimant, h("div", {}, h("div", { class: "inputgrid" }, field("Paid from fund", fund), field("Mode", mode), field("Date paid", day)),
      h("p", { class: "hint" }, "This posts a payment to the Cash Book."), h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => close() }, "Cancel"),
        h("button", { class: "btn pri", onclick: async () => { const r = await must(() => post(`/claims/${c.id}/pay`, { fund_id: fund.value, mode: mode.value, paid_on: day.value })); if (r) { close(); toast("Paid. Voucher " + r.voucher_no); draw(); } } }, "Mark paid"))));
  };
  async function draw() {
    const rows = await must(() => get("/claims" + (fs.value ? "?status=" + fs.value : ""))); if (!rows) return;
    const pend = rows.filter(r => r.status === "Pending").reduce((a, r) => a + r.amount, 0), appr = rows.filter(r => r.status === "Approved").reduce((a, r) => a + r.amount, 0);
    const mineOnly = r => r.user_id === USER.id;
    out.replaceChildren(h("div", { class: "qbar" }, `${rows.length} claim(s). Waiting for approval ${money(pend)}. Approved, not yet paid ${money(appr)}.`),
      rows.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["No", "Date", "By", "Project", "Category", "Amount", "Status", "Bill", ""].map(x => h("th", {}, x)))), h("tbody", {}, ...rows.map(c => h("tr", {},
        h("td", {}, c.claim_no), h("td", {}, fd(c.date)), h("td", {}, c.claimant), h("td", {}, c.project || "–"), h("td", {}, c.category, c.description ? h("div", { class: "hint" }, c.description) : null), h("td", { class: "n" }, money(c.amount)),
        h("td", {}, cell(c.status, "badge")[0], c.remark ? h("div", { class: "hint" }, c.remark) : null), h("td", {}, c.bills ? h("button", { class: "btn sm", onclick: () => bills(c) }, "View") : "–"),
        h("td", {}, h("div", { class: "actions", style: "margin:0" },
          fin && c.status === "Pending" && !mineOnly(c) ? [h("button", { class: "btn sm pri", onclick: () => decide(c, "approve") }, "Approve"), h("button", { class: "btn sm", onclick: () => decide(c, "reject") }, "Reject")] : null,
          fin && c.status === "Approved" && !mineOnly(c) ? h("button", { class: "btn sm pri", onclick: () => pay(c) }, "Pay") : null,
          fin && mineOnly(c) && ["Pending", "Approved"].includes(c.status) ? h("span", { class: "hint" }, "Another finance user must act on your own claim") : null,
          (mineOnly(c) || USER.role === "admin") && c.status === "Pending" ? h("button", { class: "btn sm", onclick: () => confirmBox("Withdraw this claim?", async () => { if (await must(() => del("/claims/" + c.id))) { toast("Withdrawn"); draw(); } }, "Withdraw") }, "Withdraw") : null)))))))
        : h("div", { class: "empty" }, "No claims yet."));
  }
  fs.onchange = draw; await draw();
  return h("div", {}, head("Expense claims", fin ? "Check the bill, approve, then pay. The person who made a claim cannot approve or pay it." : "Claims you have sent."), h("div", { class: "bar" }, fs, h("span", { class: "grow" }), roleOk() ? h("a", { class: "btn pri", href: "#/r/fieldclaim" }, "New claim") : null), out);
}

/* ---------------- opening with no network ---------------- */
/* After a normal sign-in the phone keeps a small snapshot (your name and role, the dropdown lists, the project list). With no signal
   the app then opens straight to the field pages, and what you enter waits on the phone and uploads later. Nothing else is stored. */
const OFFKEY = "ngo_offline_v1";
function offlineLoad() { try { const s = JSON.parse(localStorage.getItem(OFFKEY) || "null"); return s && s.user && Date.now() - s.at < 14 * 864e5 ? s : null; } catch (e) { return null; } }
function offlineSave(patch) { try { localStorage.setItem(OFFKEY, JSON.stringify({ ...JSON.parse(localStorage.getItem(OFFKEY) || "{}"), ...patch, at: Date.now() })); } catch (e) { /* storage blocked */ } }
function offlineForget() { try { localStorage.removeItem(OFFKEY); } catch (e) { /* ignore */ } }
function snapshotForOffline() {
  if (!USER || !META || !["admin", "programme"].includes(USER.role)) return;
  const L = META.lists || {}, keep = {}; for (const k of ["activity", "village", "claim_category", "mode", "age_group", "service"]) keep[k] = L[k] || [];
  const old = offlineLoad(); if (old && old.user.id !== USER.id) offlineForget();       // a different person on this phone: never reuse the old snapshot
  offlineSave({ user: { id: USER.id, username: USER.username, name: USER.name, role: USER.role }, lists: keep, roles: META.roles, settings: { org_name: META.settings.org_name, asof_override: META.settings.asof_override || "" } });
  get("/options/projects").then(r => offlineSave({ projects: r })).catch(() => { /* try next time */ });
}
async function projectOptions() {
  try { const r = await get("/options/projects"); offlineSave({ projects: r }); return r; }
  catch (e) { if (e.status === 0) { const s = offlineLoad(); if (s && s.projects) return s.projects; } throw e; }
}
function offlineBanner() { return h("div", { class: "qbar warn noprint" }, h("b", {}, "Offline: entries are saved on this phone and upload when you are back online."), h("span", { class: "grow" }), langPicker()); }
async function offlineBoot() {
  const s = offlineLoad(); if (!s) return false;
  USER = s.user; META = { roles: s.roles || {}, settings: s.settings || {}, tables: {}, lists: s.lists || {}, offline: true }; window.OFFLINE = true;
  const link = (l, href) => h("a", { href, "data-h": href }, l);
  $("#app").replaceChildren(h("div", { class: "shell" }, h("nav", { class: "side", "aria-label": "Main" }, h("div", { class: "brand" }, BRAND.product), h("div", { class: "org" }, (META.settings.org_name || "")),
    link("Field app", "#/r/field"), link("Log an activity", "#/r/fieldact"), link("Expense claim", "#/r/fieldclaim"), link("Attendance and new people", "#/r/fieldpeople")), h("main", { class: "main", id: "main" })));
  if (!/^#\/r\/field/.test(location.hash)) location.hash = "#/r/field";
  window.onhashchange = route; window.addEventListener("online", () => location.reload(), { once: true }); route();
  return true;
}
async function offlineScreen() {
  const n = (await JQ.all()).length;
  $("#app").replaceChildren(h("div", { class: "login" }, h("h1", {}, BRAND.product), h("p", {}, "No network right now."), h("p", { class: "hint" }, n ? n + " item(s) saved on this phone will upload automatically once you are online and signed in." : "Nothing is waiting on this phone. Sign in once while online to use the field app with no signal."),
    h("button", { class: "btn pri", onclick: () => location.reload() }, "Try again")));
  window.addEventListener("online", () => location.reload(), { once: true });
}
