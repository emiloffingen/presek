export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const isApiRoute = url.pathname.startsWith('/api/home') || url.pathname.startsWith('/api/news');

    if (request.method !== 'GET' || !isApiRoute) {
      return fetch(request);
    }

    // Create a cache key from the request
    const cacheUrl = new URL(request.url);
    const cacheKey = new Request(cacheUrl.toString(), request);
    const cache = caches.default;

    // Check if we have a cached response
    let response = await cache.match(cacheKey);

    if (!response) {
      // If not in cache, fetch from origin
      response = await fetch(request);

      // If response is successful, cache it
      if (response.status === 200) {
        // Clone the response to cache it
        response = new Response(response.body, response);
        // Cache for 60 seconds (1 minute) at the edge
        response.headers.set('Cache-Control', 'public, max-age=60');

        ctx.waitUntil(cache.put(cacheKey, response.clone()));
      }
    }

    return response;
  }
};
