// Пресек — Service Worker v13
// Enhanced navigation support - prioritize fresh content for HTML pages

const CACHE_NAME = 'presek-v14';
const STATIC_ASSETS = [
  '/static/modern.css?v=2026.nyt.5',
  '/static/js/main.js?v=2026.nyt.5',
  '/static/js/modules/state.js',
  '/static/js/modules/utils.js',
  '/static/js/modules/theme.js',
  '/static/js/modules/api.js',
  '/static/js/modules/ui-render.js',
  '/static/js/modules/navigation.js',
  '/static/js/modules/personalization.js',
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
  // Always fetch API calls fresh
  if (e.request.url.includes('/api/')) {
    e.respondWith(fetch(e.request).catch(() => new Response('API unavailable', { status: 503 })));
    return;
  }

  // For HTML pages (navigation), try network first, then cache
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

  // For static assets, use cache-first strategy
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
