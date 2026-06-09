export type Locale = 'sr' | 'mk';

function normalizePath(path: string): string {
  if (!path) return '/';
  return path.startsWith('/') ? path : `/${path}`;
}

export function isMkHost(hostname: string | null | undefined): boolean {
  const host = (hostname || '').split(':')[0].toLowerCase();
  return host === 'presek.mk' || host === 'www.presek.mk';
}

export function stripMkPrefix(pathname: string): string {
  const path = normalizePath(pathname);
  if (path === '/mk') return '/';
  if (path.startsWith('/mk/')) {
    const stripped = path.slice(3);
    return stripped || '/';
  }
  return path;
}

export function withMkPrefix(pathname: string): string {
  const path = normalizePath(pathname);
  if (path === '/') return '/mk';
  if (path === '/mk' || path.startsWith('/mk/')) return path;
  return `/mk${path}`;
}

export function siteOrigin(lang: Locale): string {
  return lang === 'sr' ? 'https://presek.live' : 'https://presek.mk';
}

/** Public site path for links and redirects (never exposes /mk on presek.mk). */
export function localePath(path: string, lang: Locale, hostname?: string | null): string {
  const clean = stripMkPrefix(normalizePath(path));

  if (lang === 'sr') {
    return clean;
  }

  if (hostname && isMkHost(hostname)) {
    return clean;
  }

  if (clean === '/') return '/mk';
  return withMkPrefix(clean);
}

/** Client-side helper for React islands (uses window hostname when available). */
export function localePathForLang(path: string, lang: Locale): string {
  const hostname = typeof window !== 'undefined' ? window.location.hostname : null;
  return localePath(path, lang, hostname);
}

export function homePath(lang: Locale, hostname?: string | null): string {
  return localePath('/', lang, hostname);
}

export function absoluteLocaleUrl(path: string, lang: Locale): string {
  const publicPath = lang === 'mk' ? stripMkPrefix(normalizePath(path)) : normalizePath(path);
  const origin = siteOrigin(lang);
  if (publicPath === '/') return origin;
  return `${origin}${publicPath}`;
}

export function hreflangAlternates(pathname: string): { sr: string; mk: string } {
  const publicPath = stripMkPrefix(pathname).replace(/\/+$/, '');
  const suffix = publicPath && publicPath !== '/' ? publicPath : '';
  return {
    sr: `https://presek.live${suffix}`,
    mk: `https://presek.mk${suffix}`,
  };
}

export function buildCanonicalUrl(pathname: string, lang: Locale): string {
  const publicPath = stripMkPrefix(pathname).replace(/\/+$/, '');
  const origin = siteOrigin(lang);
  if (!publicPath || publicPath === '/') return origin;
  return `${origin}${publicPath}`;
}

export function isHealthyStatus(status: string | null | undefined): boolean {
  return status === 'ok' || status === 'healthy';
}

const SKIP_MK_REWRITE_PREFIXES = [
  '/api',
  '/_astro',
  '/static',
  '/proxy',
  '/img',
  '/cdn-cgi',
  '/.well-known',
  '/manifest.json',
  '/sw.js',
  '/robots.txt',
  '/sitemap',
  '/rss',
  '/og',
  '/sr',
];

export function shouldRewriteMkDomainToInternal(pathname: string): boolean {
  if (pathname === '/mk' || pathname.startsWith('/mk/')) return false;
  for (const prefix of SKIP_MK_REWRITE_PREFIXES) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`) || pathname.startsWith(`${prefix}.`)) {
      return false;
    }
  }
  if (/\.[a-z0-9]+$/i.test(pathname) && !pathname.endsWith('.html')) return false;
  return true;
}

export function isMkContext(lang: Locale, hostname?: string | null, pathname?: string | null): boolean {
  if (lang === 'mk') return true;
  if (hostname && isMkHost(hostname)) return true;
  if (pathname && (pathname === '/mk' || pathname.startsWith('/mk/'))) return true;
  return false;
}
