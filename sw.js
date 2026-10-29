/* P-51 service worker: the whole game is one HTML file, so cache it and the icons and it runs offline.
   Pages are fetched from the network first (cache is the offline fallback), so an update shows on the next launch. */
const CACHE = 'p51-v2';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './icon-maskable-512.png', './apple-touch-icon.png'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;
  /* network first, so a new version shows on the next launch; the cache is the fallback when offline or the network is slow (3 s) */
  e.respondWith(
    new Promise((resolve) => {
      const miss = () => caches.match(e.request, { ignoreSearch: true });
      const timer = setTimeout(() => miss().then((h) => h && resolve(h)), 3000);
      fetch(e.request, { cache: 'no-cache' })
        .then((r) => {
          clearTimeout(timer);
          if (r && r.ok) caches.open(CACHE).then((c) => c.put(e.request, r.clone()));
          resolve(r);
        })
        .catch(() => {
          clearTimeout(timer);
          miss().then((h) => resolve(h || Response.error()));
        });
    }),
  );
});
