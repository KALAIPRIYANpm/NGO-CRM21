/* Service worker: lets the app open with no network. Pages and scripts are fetched fresh when online
   (so updates always arrive) and fall back to the last copy when offline. Data (/api/) is never cached,
   so nobody ever sees stale money figures or someone else's photos. */
const CACHE = "ngo-shell-v15b";
const SHELL = ["/", "/index.html", "/style.css", "/app.js", "/views.js", "/auto.js", "/comm.js", "/lang.js", "/lang_extra.js", "/field.js", "/security.js", "/impact.js", "/inbox.js", "/care.js", "/partners.js", "/v10.js", "/v11.js", "/v12.js", "/v13.js", "/v14.js", "/theme.js", "/prints.js"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  e.respondWith(fetch(r).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(r, copy)); }
    return res;
  }).catch(() => caches.match(r).then(m => m || (r.mode === "navigate" ? caches.match("/index.html") : Response.error()))));
});
