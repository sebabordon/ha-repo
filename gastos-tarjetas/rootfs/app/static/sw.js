/* Finance Me — service worker (minimal, cache-first for statics) */
const CACHE = "finance-me-v0.2.36";
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

// ── Web Push ──────────────────────────────────────────────────────────────────
self.addEventListener("push", e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; }
  catch (_) { data = { body: e.data ? e.data.text() : "" }; }
  const title = data.title || "Finance Me";
  e.waitUntil(self.registration.showNotification(title, {
    body:  data.body || "",
    icon:  "/static/icono-sb.png",
    badge: "/static/icono-sb.png",
    data:  { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if ("focus" in c) { c.navigate(url); return c.focus(); }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
