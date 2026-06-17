/** Shared service-worker API cache policy (imported by /sw.js). */

export const API_CACHE_DENY_PREFIXES = [
  '/api/profile',
  '/api/admin',
  '/api/csrf-token',
  '/api/delivery',
  '/api/health',
  '/api/metrics',
  '/api/newsletter',
  '/api/intelligence',
  '/api/v1/profile',
  '/api/v1/admin',
  '/api/v1/csrf-token',
  '/api/v1/delivery',
  '/api/v1/health',
  '/api/v1/metrics',
  '/api/v1/newsletter',
  '/api/v1/intelligence',
];

export const API_CACHE_ALLOW_PREFIXES = [
  '/api/home',
  '/api/news',
  '/api/archive',
  '/api/trending',
  '/api/search',
  '/api/cluster/',
  '/api/entity-graph/',
  '/api/intelligence/briefing',
  '/api/stats/',
  '/api/v1/home',
  '/api/v1/news',
  '/api/v1/archive',
  '/api/v1/trending',
  '/api/v1/search',
  '/api/v1/cluster/',
  '/api/v1/entity-graph/',
  '/api/v1/intelligence/briefing',
  '/api/v1/stats/',
];

export function shouldCacheApiPath(pathname) {
  if (!pathname || !pathname.startsWith('/api/')) {
    return false;
  }
  if (API_CACHE_DENY_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return false;
  }
  return API_CACHE_ALLOW_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function shouldStoreApiResponse(response) {
  if (!response || response.status !== 200) {
    return false;
  }
  const cacheControl = (response.headers.get('cache-control') || '').toLowerCase();
  if (cacheControl.includes('no-store') || cacheControl.includes('private')) {
    return false;
  }
  return true;
}
