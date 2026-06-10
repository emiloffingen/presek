// Presek — Service Worker v28
// Astro-only frontend caching: Stale-While-Revalidate for API and Cache-First for static assets

const CACHE_NAME = 'presek-v28';
const API_CACHE_NAME = 'presek-api-v28';
const API_CACHE_MAX_AGE_MS = 5 * 60 * 1000; // 5 minutes max staleness for API

// Core static assets that are shared across the Astro frontend
const STATIC_ASSETS = [
  '/logo.svg?v=3',
  '/img/presek_emblem.svg?v=3',
  '/img/icons/presek-icon-192.png',
  '/img/icons/presek-icon-512.png',
  '/img/icons/presek-maskable-192.png',
  '/img/icons/presek-maskable-512.png',
  '/img/icons/presek-apple-touch.png',
  '/img/placeholder.svg',
  '/manifest.json',
  '/offline',
];

function offlineApiResponse() {
  return new Response(JSON.stringify({ status: 'offline' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json; charset=utf-8' }
  });
}

function offlinePageFor(url) {
  return '/offline';
}

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
  if (e.request.method !== 'GET') return;

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
          return fetchPromise.then(net => net || cachedResponse || offlineApiResponse());
        });
      })
    );
    return;
  }

  // Cache-First for typography and font resources (woff2, woff, ttf, etc.)
  if (
    url.pathname.endsWith('.woff2') || 
    url.pathname.endsWith('.woff') || 
    url.pathname.endsWith('.ttf') || 
    url.hostname.includes('fonts.gstatic.com') ||
    url.hostname.includes('fonts.googleapis.com')
  ) {
    e.respondWith(
      caches.open(CACHE_NAME).then(cache => {
        return cache.match(e.request).then(cachedResponse => {
          if (cachedResponse) return cachedResponse;
          return fetch(e.request).then(networkResponse => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(e.request, networkResponse.clone());
            }
            return networkResponse;
          });
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
      }).catch(async () => {
        const cached = await caches.match(e.request);
        if (cached) return cached;
        const localizedOffline = await caches.match(offlinePageFor(url));
        return localizedOffline || caches.match('/offline');
      })
    );
    return;
  }

  // Default: Network only or Cache-First for other assets
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

// Background Prefetching Handler
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'PREFETCH_URLS') {
    const urls = event.data.urls || [];
    caches.open(CACHE_NAME).then(cache => {
      urls.forEach(url => {
        cache.match(url).then(cachedResponse => {
          if (!cachedResponse) {
            fetch(url).then(networkResponse => {
              if (networkResponse && networkResponse.status === 200) {
                cache.put(url, networkResponse);
              }
            }).catch(() => {
              // Ignore safe background network failures
            });
          }
        });
      });
    });
  }
});
