/**
 * Resolve the API base URL.
 *
 * Astro frontmatter only ever runs server-side, so the SSR fallback is what
 * matters there. React islands run client-side after hydration, so they get
 * the relative `/api` path that nginx proxies to the backend.
 *
 * IMPORTANT: PUBLIC_API_URL is inlined into the client bundle at build time.
 * A value pointing at loopback (the internal container URL, e.g.
 * http://127.0.0.1:5001/api) must NEVER be handed to the browser, so for
 * client-side callers we always prefer the relative `/api` and only accept an
 * absolute PUBLIC_API_URL when it is a real public origin.
 */
function isBrowserSafeApiBase(value: string): boolean {
  if (!value) return false;
  if (value.startsWith('/')) return true; // relative, always safe
  try {
    const host = new URL(value).hostname;
    return !(host === '127.0.0.1' || host === 'localhost' || host === '::1' || host === '0.0.0.0');
  } catch {
    return false;
  }
}

export function apiBaseUrl(): string {
  const fromEnv = import.meta.env?.PUBLIC_API_URL;

  if (typeof window !== 'undefined') {
    // Client: never use a loopback/internal URL.
    return isBrowserSafeApiBase(fromEnv || '') && (fromEnv as string).startsWith('/')
      ? (fromEnv as string)
      : '/api';
  }

  // Server (SSR): allow the internal URL for server-side fetches.
  if (fromEnv) return fromEnv;
  return (typeof process !== 'undefined' && process.env.INTERNAL_API_URL)
    || 'http://127.0.0.1:5001/api';
}

export function proxyBaseUrl(): string {
  const apiBase = import.meta.env?.PUBLIC_API_URL || '';
  if (!apiBase || !isBrowserSafeApiBase(apiBase)) return '';
  if (apiBase.startsWith('/')) return '';

  try {
    const url = new URL(apiBase, 'https://presek.mk');
    if (url.pathname.endsWith('/api')) {
      url.pathname = url.pathname.slice(0, -4) || '/';
    }
    url.search = '';
    url.hash = '';
    return url.origin + (url.pathname === '/' ? '' : url.pathname.replace(/\/$/, ''));
  } catch {
    return '';
  }
}

export function proxyUrl(pathAndSearch: string): string {
  const base = proxyBaseUrl();
  const path = pathAndSearch.startsWith('/') ? pathAndSearch : `/${pathAndSearch}`;
  return `${base}${path}`;
}
