// Пресек — Service Worker v6
// Caches the shell for instant loads and allows offline reading of recently viewed clusters

const CACHE_NAME = 'presek-v6';
const STATIC_ASSETS = [
  '/',
  '/static/modern.css',
  '/static/logo.svg',
  '/static/logo.png',
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

  // 1. API Calls: Network only, with a custom "Offline" response for news
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request).catch(async () => {
        if (url.pathname.includes('/api/news')) {
            // Return an empty cluster set instead of a hard error
            return new Response(JSON.stringify({ clusters: [], has_more: false, offline: true }), {
                headers: { 'Content-Type': 'application/json' }
            });
        }
        return new Response(null, { status: 503 });
    }));
    return;
  }

  // 2. Navigation & Clusters: Stale-while-revalidate for recently read clusters
  if (e.request.mode === 'navigate' || url.pathname.startsWith('/cluster/')) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        const networkFetch = fetch(e.request).then(resp => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          }
          return resp;
        });
        return cached || networkFetch;
      })
    );
    return;
  }

  // 3. General Assets: Cache first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
      if (resp && resp.status === 200 && e.request.method === 'GET') {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
      }
      return resp;
    }))
  );
});
