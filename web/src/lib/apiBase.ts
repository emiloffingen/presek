/**
 * Resolve the API base URL.
 *
 * Astro frontmatter only ever runs server-side, so the SSR fallback is what
 * matters there. React islands run client-side after hydration, so they get
 * the relative `/api` path that nginx proxies to the backend.
 */
export function apiBaseUrl(): string {
  const fromEnv = import.meta.env.PUBLIC_API_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined') return '/api';
  
  // SSR fallback: use internal container URL if available
  // In Astro, server-side process.env can be accessed
  return (typeof process !== 'undefined' && process.env.INTERNAL_API_URL) 
    || 'http://127.0.0.1:5001/api';
}
