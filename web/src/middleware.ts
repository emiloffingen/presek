import { defineMiddleware } from 'astro:middleware';
import {
  stripMkPrefix,
} from './lib/localePaths';
import { buildCspPolicy, computeInlineHashes, generateCspNonce } from './lib/csp';
import { timingSafeEqual } from 'node:crypto';

export const onRequest = defineMiddleware(async (context, next) => {
  const url = new URL(context.request.url);
  const host = context.request.headers.get('host') || url.hostname;
  const hostname = host.split(':')[0].toLowerCase();
  const pathname = url.pathname;

  const retiredPublicPrefixes = [
    '/for-you', '/briefing', '/pulse', '/graf', '/grafik',
    '/settings', '/pregled', '/analize', '/debug',
  ];
  if (
    (hostname === 'presek.mk' || hostname === 'www.presek.mk')
    && retiredPublicPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
  ) {
    return Response.redirect(new URL(`/${url.search}`, 'https://presek.mk'), 302);
  }

  if (hostname === 'presek.live' || hostname === 'www.presek.live') {
    const targetPath = stripMkPrefix(pathname) || '/';
    const target = new URL(`${targetPath}${url.search}`, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && (pathname === '/mk' || pathname.startsWith('/mk/'))) {
    const targetPath = stripMkPrefix(pathname) || '/';
    const target = new URL(`${targetPath}${url.search}`, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  const cspNonce = generateCspNonce();
  context.locals.cspNonce = cspNonce;

  const isProductionHost =
    hostname === 'presek.live'
    || hostname === 'www.presek.live'
    || hostname === 'presek.mk'
    || hostname === 'www.presek.mk';

  // Static hardening headers (mirrors routes/security.py). Applied to every
  // response; HSTS uses the full preload value only on production hosts.
  const staticSecurityHeaders: Record<string, string> = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer-when-downgrade',
    'Permissions-Policy':
      'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
    'Strict-Transport-Security': isProductionHost
      ? 'max-age=63072000; includeSubDomains; preload'
      : 'max-age=300; includeSubDomains',
  };

  const attachSecurityHeaders = async (response: Response) => {
    for (const [name, value] of Object.entries(staticSecurityHeaders)) {
      response.headers.set(name, value);
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      const body = await response.text();
      const hashes = computeInlineHashes(body);
      response.headers.set('Content-Security-Policy', buildCspPolicy(cspNonce, hashes));
      // Public, anonymous HTML is safe to cache at the edge. max-age=0 keeps
      // browsers from caching (so users never see stale-after-deploy HTML),
      // s-maxage lets Cloudflare serve it without touching this host, and
      // stale-while-revalidate/stale-if-error let the edge ride out brief
      // origin outages instead of returning 530/502. Admin and API responses
      // are never cached.
      const cacheableHtml =
        context.request.method === 'GET'
        && !pathname.startsWith('/admin')
        && !pathname.startsWith('/api/')
        && !pathname.startsWith('/dev')
        && !response.headers.has('set-cookie');
      if (cacheableHtml) {
        // Deliberately NO s-maxage: in Cloudflare, s-maxage implies
        // proxy-revalidate and DISABLES stale-while-revalidate / stale-if-error.
        // Edge TTL is controlled by the "static edge cache" Cache Rules; these
        // directives let the edge serve stale during background revalidation and
        // on origin 5xx (e.g. a cloudflared tunnel outage) instead of 530/502.
        response.headers.set('Cache-Control', 'public, max-age=0, stale-while-revalidate=300, stale-if-error=86400');
      }
      // Preserve any other headers; clone the body into a new Response so the
      // consumed stream remains readable downstream.
      const { status, statusText } = response;
      const init: ResponseInit = { status, statusText, headers: response.headers };
      return new Response(body, init);
    }
    return response;
  };

  if (isProductionHost && pathname.startsWith('/dev')) {
    return new Response('Not found', { status: 404 });
  }

  // /admin is token-gated on production; /admin/status stays public. Deny by
  // default when no token is configured so the dashboard is never exposed.
  if (isProductionHost && pathname.startsWith('/admin') && pathname !== '/admin/status') {
    const adminPageToken = process.env.ADMIN_PAGE_TOKEN?.trim();
    if (!adminPageToken) {
      return new Response('Not found', { status: 404 });
    }
    const provided = context.request.headers.get('x-admin-page-token') || '';
    const expected = Buffer.from(adminPageToken);
    const actual = Buffer.from(provided);
    if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) {
      return new Response('Not found', { status: 404 });
    }
  }

  return attachSecurityHeaders(await next());
});
