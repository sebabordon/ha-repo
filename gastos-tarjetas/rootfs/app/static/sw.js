/* Gastos — service worker (minimal, cache-first for statics) */
const CACHE = "gastos-v0.2.32";
const PRECACHE = ["/", "/static/app.js", "/static/style.css"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  // Never intercept non-GET, API, auth or admin requests
  if (
    e.request.method !== "GET" ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/auth/") ||
    url.pathname.startsWith("/admin")
  ) return;

  if (url.pathname.startsWith("/static/")) {
    // Static assets: cache-first, update in background
    e.respondWith(
      caches.match(e.request).then(cached => {
        const fresh = fetch(e.request).then(res => {
          caches.open(CACHE).then(c => c.put(e.request, res.clone()));
          return res;
        });
        return cached || fresh;
      })
    );
  } else {
    // Navigation (/, /manifest.json, etc.): network-first
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  }
});
