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
export function apiBaseUrl(): string {
  // Client (browser): always use the relative /api. Never a loopback/internal
  // URL — PUBLIC_API_URL is baked in at build time and .env holds the internal
  // container address, which no browser can reach.
  if (typeof window !== 'undefined') {
    return '/api';
  }

  // Server (SSR): Node fetch needs an absolute URL, so use the internal one.
  const fromEnv = import.meta.env?.PUBLIC_API_URL;
  if (fromEnv && !fromEnv.startsWith('/')) return fromEnv;
  return (typeof process !== 'undefined' && process.env.INTERNAL_API_URL)
    || 'http://127.0.0.1:5001/api';
}

export function proxyBaseUrl(): string {
  const apiBase = import.meta.env?.PUBLIC_API_URL || '';
  if (!apiBase || apiBase.startsWith('/')) return '';
  // A loopback/internal origin is not a public proxy origin.
  try {
    const host = new URL(apiBase).hostname;
    if (host === '127.0.0.1' || host === 'localhost' || host === '::1' || host === '0.0.0.0') return '';
  } catch {
    return '';
  }

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
