import { defineMiddleware } from 'astro:middleware';
import {
  shouldRewriteMkDomainToInternal,
  stripMkPrefix,
  withMkPrefix,
} from './lib/localePaths';

export const onRequest = defineMiddleware((context, next) => {
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

  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && shouldRewriteMkDomainToInternal(pathname)) {
    const internalPath = withMkPrefix(pathname);
    if (internalPath !== pathname) {
      return next(`${internalPath}${url.search}`);
    }
  }

  return next();
});
