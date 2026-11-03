/* Le Brief Invest : service worker (appli installable + ouverture rapide).
   Pages et données : réseau d'abord (toujours à jour), copie de secours si pas de connexion.
   Images et logos : copie locale, rafraîchie en arrière-plan. Rien n'est touché hors du site (audio, comptes, graphiques). */
const VERSION = "lb-v10";
const SHELL = ["./", "index.html", "manifest.webmanifest", "img/logo.svg", "img/icon-192.png", "img/icon-512.png", "favicon.svg", "apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function keyOf(req) {               // les ?t=123 anti-cache ne créent pas une copie par appel
  const u = new URL(req.url); u.search = ""; u.hash = ""; return u.toString();
}
async function networkFirst(req, key) {
  const c = await caches.open(VERSION);
  try {
    const res = await fetch(req);
    if (res && res.ok) c.put(key, res.clone());
    return res;
  } catch (err) {
    const hit = await c.match(key) || (req.mode === "navigate" ? await c.match("index.html") : null);
    if (hit) return hit;
    throw err;
  }
}
async function staleWhileRevalidate(req) {
  const c = await caches.open(VERSION);
  const hit = await c.match(req);
  const net = fetch(req).then(res => { if (res && res.ok) c.put(req, res.clone()); return res; }).catch(() => hit);
  return hit || net;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;            // audio, Supabase, TradingView… : on ne touche pas
  if (req.headers.get("range")) return;                        // lecture audio par morceaux
  if (req.mode === "navigate" || url.pathname.endsWith(".html")) { e.respondWith(networkFirst(req, keyOf(req))); return; }
  if (url.pathname.endsWith(".json")) { e.respondWith(networkFirst(req, keyOf(req))); return; }
  if (/\.(png|jpe?g|svg|webp|gif|ico|webmanifest)$/i.test(url.pathname)) { e.respondWith(staleWhileRevalidate(req)); return; }
});

/* Notifications du site (alertes envoyées par le robot) */
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: "Le Brief Invest", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Le Brief Invest", {
    body: d.body || "", icon: "img/icon-192.png", badge: "img/icon-192.png", tag: d.tag || undefined,
    data: { url: d.url || "./#general" }, renotify: !!d.tag
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "./#general";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    const same = list.find(c => c.url.startsWith(self.registration.scope));
    if (same && url.startsWith(self.registration.scope)) { same.focus(); return same.navigate(url).catch(() => {}); }
    return self.clients.openWindow(url);
  }));
});
