// Пресек — Service Worker v7 (Hybrid 5.1)
// Optimized for Instant Loads + Offline Reliability

const CACHE_NAME = 'presek-v7';
const STATIC_ASSETS = [
  '/',
  '/static/modern.css',
  '/static/js/ui.js',
  '/static/js/app.js',
  '/static/logo.svg',
  '/static/img/presek_emblem.svg',
  '/static/img/placeholder.svg'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // 1. API: Network Only, fallback to offline response
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request).catch(async () => {
        if (url.pathname.includes('/api/news')) {
            return new Response(JSON.stringify({ status: 'success', clusters: [], has_more: false, offline: true }), {
                headers: { 'Content-Type': 'application/json' }
            });
        }
        return new Response(null, { status: 503 });
    }));
    return;
  }

  // 2. Navigation & Clusters: Stale-While-Revalidate
  if (e.request.mode === 'navigate' || url.pathname.startsWith('/cluster/')) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        const networkFetch = fetch(e.request).then(resp => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          }
          return resp;
        }).catch(() => null);
        return cached || networkFetch;
      })
    );
    return;
  }

  // 3. Static Assets: Cache First
  e.respondWith(
    caches.match(e.request).then(cached => {
      return cached || fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && e.request.method === 'GET') {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        }
        return resp;
      });
    })
  );
});
