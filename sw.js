// Пресек — Service Worker v10
// Forced Refresh for Identical NYT Style

const CACHE_NAME = 'presek-v10';
const STATIC_ASSETS = [
  '/',
  '/static/modern.css?v=2026.final.1',
  '/static/js/ui.js?v=2026.final.1',
  '/static/js/app.js?v=2026.final.1',
  '/static/logo.svg',
  '/static/img/presek_emblem.svg'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Bypassing cache for API calls to ensure fresh data
  if (e.request.url.includes('/api/')) {
    e.respondWith(fetch(e.request));
    return;
  }

  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && e.request.method === 'GET') {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        }
        return resp;
      });
    })
  );
});
