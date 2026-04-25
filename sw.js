// Пресек — Системски Service Worker v5.4
// Уредничка оптимизација за офлајн пристап и семантичко кеширање

const CACHE_NAME = 'presek-core-v5.4';
const API_CACHE_NAME = 'presek-intel-v5.4';
const OFFLINE_URL = '/offline';

const STATIC_ASSETS = [
  '/',
  OFFLINE_URL,
  '/static/logo.svg?v=3',
  '/static/img/presek_emblem.svg?v=3',
  '/static/img/placeholder.svg',
  '/static/manifest.json'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME && k !== API_CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  const isHtml = e.request.headers.get('accept')?.includes('text/html');

  // 1. API Caching (Stale-While-Revalidate)
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      caches.open(API_CACHE_NAME).then(cache => {
        return cache.match(e.request).then(cached => {
          const fetchPromise = fetch(e.request).then(network => {
            if (network.status === 200) cache.put(e.request, network.clone());
            return network;
          }).catch(() => null);
          return cached || fetchPromise;
        });
      })
    );
    return;
  }

  // 2. Navigation with Offline Fallback
  if (isHtml) {
    e.respondWith(
      fetch(e.request)
        .then(network => {
          if (network.status === 200) {
              const clone = network.clone();
              caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          }
          return network;
        })
        .catch(async () => {
          const cached = await caches.match(e.request);
          if (cached) return cached;
          return caches.match(OFFLINE_URL);
        })
    );
    return;
  }

  // 3. Static Assets (Cache-First)
  e.respondWith(
    caches.match(e.request).then(cached => {
      return cached || fetch(e.request).then(network => {
          if (network.status === 200 && (url.pathname.includes('/img/') || url.pathname.includes('/_astro/'))) {
              caches.open(CACHE_NAME).then(c => c.put(e.request, network.clone()));
          }
          return network;
      });
    })
  );
});
