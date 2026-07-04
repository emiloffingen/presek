import { defineMiddleware } from 'astro:middleware';
import {
  shouldRewriteMkDomainToInternal,
  stripMkPrefix,
  withMkPrefix,
} from './lib/localePaths';
import { buildCspPolicy, generateCspNonce } from './lib/csp';
import { timingSafeEqual } from 'node:crypto';

export const onRequest = defineMiddleware(async (context, next) => {
  const url = new URL(context.request.url);
  const host = context.request.headers.get('host') || url.hostname;
  const hostname = host.split(':')[0].toLowerCase();
  const pathname = url.pathname;

  if ((hostname === 'presek.live' || hostname === 'www.presek.live') && pathname.startsWith('/mk')) {
    const targetPath = stripMkPrefix(pathname) || '/';
    const target = new URL(`${targetPath}${url.search}`, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && pathname.startsWith('/sr')) {
    const targetPath = pathname.replace(/^\/sr/, '') || '/';
    const target = new URL(`${targetPath}${url.search}`, 'https://presek.live');
    return Response.redirect(target, 301);
  }

  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && (pathname === '/mk' || pathname.startsWith('/mk/'))) {
    const targetPath = stripMkPrefix(pathname) || '/';
    const target = new URL(`${targetPath}${url.search}`, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  const cspNonce = generateCspNonce();
  context.locals.cspNonce = cspNonce;

  const attachFrameAncestors = async (response: Response) => {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      response.headers.set('Content-Security-Policy', buildCspPolicy(cspNonce));
    }
    return response;
  };

  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && shouldRewriteMkDomainToInternal(pathname)) {
    const internalPath = withMkPrefix(pathname);
    if (internalPath !== pathname) {
      return attachFrameAncestors(await next(`${internalPath}${url.search}`));
    }
  }

  const isProductionHost =
    hostname === 'presek.live'
    || hostname === 'www.presek.live'
    || hostname === 'presek.mk'
    || hostname === 'www.presek.mk';

  if (isProductionHost && pathname.startsWith('/dev')) {
    return new Response('Not found', { status: 404 });
  }

  const adminPageToken = process.env.ADMIN_PAGE_TOKEN?.trim();
  if (
    isProductionHost
    && adminPageToken
    && pathname.startsWith('/admin')
    && pathname !== '/admin/status'
  ) {
    const provided = context.request.headers.get('x-admin-page-token') || '';
    const expected = Buffer.from(adminPageToken);
    const actual = Buffer.from(provided);
    if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) {
      return new Response('Not found', { status: 404 });
    }
  }

  return attachFrameAncestors(await next());
});
