// Presek — Service Worker v24
// Astro-only frontend caching: Stale-While-Revalidate for API and Cache-First for static assets

const CACHE_NAME = 'presek-v24';
const API_CACHE_NAME = 'presek-api-v24';
const API_CACHE_MAX_AGE_MS = 5 * 60 * 1000; // 5 minutes max staleness for API

// Core static assets that are shared across the Astro frontend
const STATIC_ASSETS = [
  '/logo.svg?v=3',
  '/img/presek_emblem.svg?v=3',
  '/img/placeholder.svg',
  '/manifest.json'
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

  // Stale-While-Revalidate for API calls (with max-age enforcement)
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      caches.open(API_CACHE_NAME).then(cache => {
        return cache.match(e.request).then(cachedResponse => {
          const fetchPromise = fetch(e.request).then(networkResponse => {
            if (networkResponse && networkResponse.status === 200) {
              // Store response with timestamp header for TTL enforcement
              const headers = new Headers(networkResponse.headers);
              headers.set('sw-cached-at', Date.now().toString());
              const timedResponse = new Response(networkResponse.clone().body, {
                status: networkResponse.status,
                statusText: networkResponse.statusText,
                headers
              });
              cache.put(e.request, timedResponse);
            }
            return networkResponse;
          }).catch(() => null);

          // Check if cached response is still fresh
          if (cachedResponse) {
            const cachedAt = parseInt(cachedResponse.headers.get('sw-cached-at') || '0', 10);
            if (cachedAt && (Date.now() - cachedAt) > API_CACHE_MAX_AGE_MS) {
              // Stale — prefer network, fall back to stale cache
              return fetchPromise.then(net => net || cachedResponse);
            }
            return cachedResponse;
          }
          return fetchPromise;
        });
      })
    );
    return;
  }

  // Cache-First for static assets
  if (url.pathname.startsWith('/img/')) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(resp => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  // Network-First for HTML pages (navigation)
  if (e.request.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request).then(resp => {
        if (resp && resp.status === 200) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Default: Network only or Cache-First for other assets
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
