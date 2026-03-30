// Пресек — Service Worker
// Caches the shell (HTML/CSS/JS) for instant loads; news always fetched fresh

const CACHE = 'presek-v5';
const SHELL = [
  '/',
  '/static/modern.css',
  '/static/logo.svg'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Always fetch API calls fresh — never cache news data
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request).catch(() =>
      new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } })
    ));
    return;
  }

  // Assets and Shell: cache-first with network fallback
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
      // Don't cache dynamic pages (like cluster/123) unless we want offline reading
      // For now, only cache what's in the shell or explicit static assets
      if (resp && resp.status === 200 && e.request.method === 'GET') {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
      }
      return resp;
    }))
  );
});
