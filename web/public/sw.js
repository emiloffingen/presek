// Presek — Service Worker v30
// Allowlisted stale-while-revalidate for public API reads only.

import { shouldCacheApiPath, shouldStoreApiResponse } from './sw-cache-policy.js';

const CACHE_NAME = 'presek-v30';
const API_CACHE_NAME = 'presek-api-v30';
const API_CACHE_MAX_AGE_MS = 5 * 60 * 1000;

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

function networkOnly(request) {
  return fetch(request);
}

function staleWhileRevalidate(request, cache) {
  return cache.match(request).then((cachedResponse) => {
    const fetchPromise = fetch(request).then((networkResponse) => {
      if (shouldStoreApiResponse(networkResponse)) {
        const headers = new Headers(networkResponse.headers);
        headers.set('sw-cached-at', Date.now().toString());
        const timedResponse = new Response(networkResponse.clone().body, {
          status: networkResponse.status,
          statusText: networkResponse.statusText,
          headers
        });
        cache.put(request, timedResponse);
      }
      return networkResponse;
    }).catch(() => null);

    if (cachedResponse) {
      const cachedAt = parseInt(cachedResponse.headers.get('sw-cached-at') || '0', 10);
      if (cachedAt && (Date.now() - cachedAt) > API_CACHE_MAX_AGE_MS) {
        return fetchPromise.then((net) => net || cachedResponse);
      }
      return cachedResponse;
    }

    return fetchPromise.then((net) => net || cachedResponse || offlineApiResponse());
  });
}

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_NAME && k !== API_CACHE_NAME).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;

  const url = new URL(e.request.url);

  if (url.pathname.startsWith('/api/')) {
    if (!shouldCacheApiPath(url.pathname)) {
      e.respondWith(networkOnly(e.request));
      return;
    }

    e.respondWith(
      caches.open(API_CACHE_NAME).then((cache) => staleWhileRevalidate(e.request, cache))
    );
    return;
  }

  if (
    url.pathname.endsWith('.woff2') ||
    url.pathname.endsWith('.woff') ||
    url.pathname.endsWith('.ttf') ||
    url.hostname.includes('fonts.gstatic.com') ||
    url.hostname.includes('fonts.googleapis.com')
  ) {
    e.respondWith(
      caches.open(CACHE_NAME).then((cache) => cache.match(e.request).then((cachedResponse) => {
        if (cachedResponse) return cachedResponse;
        return fetch(e.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            cache.put(e.request, networkResponse.clone());
          }
          return networkResponse;
        });
      }))
    );
    return;
  }

  if (url.pathname.startsWith('/img/')) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        if (cached) return cached;
        return fetch(e.request).then((resp) => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  if (e.request.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request).then((resp) => {
        if (resp && resp.status === 200) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
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

  e.respondWith(
    caches.match(e.request).then((cached) => cached || fetch(e.request))
  );
});

self.addEventListener('push', (event) => {
  let payload = { title: 'Presek', message: '', click_url: '/' };
  try {
    if (event.data) {
      payload = { ...payload, ...event.data.json() };
    }
  } catch (_) {
    // Ignore malformed push payloads
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || 'Presek', {
      body: payload.message || '',
      icon: '/img/icons/presek-icon-192.png',
      badge: '/img/icons/presek-maskable-192.png',
      data: { url: payload.click_url || '/' },
      tag: 'presek-briefing',
      renotify: true,
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if ('focus' in client) {
          if ('navigate' in client) {
            return client.navigate(targetUrl).then(() => client.focus());
          }
          return client.focus();
        }
      }
      return clients.openWindow(targetUrl);
    })
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'PREFETCH_URLS') {
    const urls = event.data.urls || [];
    caches.open(CACHE_NAME).then((cache) => {
      urls.forEach((url) => {
        if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('/api/')) {
          return;
        }
        cache.match(url).then((cachedResponse) => {
          if (!cachedResponse) {
            fetch(url).then((networkResponse) => {
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
