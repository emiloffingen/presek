// Пресек — Service Worker v22
// Combined Caching (Stale-While-Revalidate) and Web Push Support

const CACHE_NAME = 'presek-v22';
const API_CACHE_NAME = 'presek-api-v22';

const STATIC_ASSETS = [
  '/',
  '/logo.svg',
  '/img/presek_emblem.svg',
  '/img/presek_emblem.png',
  '/manifest.json'
];

// 1. Install & Activate
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

// 2. Fetch Logic (Caching)
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API Caching: Stale-While-Revalidate
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      caches.open(API_CACHE_NAME).then(cache => {
        return cache.match(e.request).then(cachedResponse => {
          const fetchPromise = fetch(e.request).then(networkResponse => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(e.request, networkResponse.clone());
            }
            return networkResponse;
          }).catch(() => null);
          return cachedResponse || fetchPromise;
        });
      })
    );
    return;
  }

  // Network-First for navigation
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

  // Cache-First for static assets
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

// 3. Web Push Logic
self.addEventListener('push', function(event) {
  if (event.data) {
    let payload = {};
    try {
      payload = event.data.json();
    } catch (e) {
      payload = { title: "Пресек", message: event.data.text() };
    }
    
    event.waitUntil(
      self.registration.showNotification(payload.title || "Пресек", {
        body: payload.message || "Ново известување",
        icon: '/img/presek_emblem.png',
        badge: '/img/presek_emblem.png',
        data: { url: payload.click_url || '/' },
        vibrate: [200, 100, 200]
      })
    );
  }
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      for (let i = 0; i < windowClients.length; i++) {
        let client = windowClients[i];
        if (client.url.includes(event.notification.data.url) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data.url);
      }
    })
  );
});
