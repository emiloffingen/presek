import { defineMiddleware } from 'astro:middleware';

export const onRequest = defineMiddleware((context, next) => {
  const url = new URL(context.request.url);
  const host = context.request.headers.get('host') || url.hostname;
  const hostname = host.split(':')[0].toLowerCase();

  if ((hostname === 'presek.live' || hostname === 'www.presek.live') && url.pathname.startsWith('/mk')) {
    const target = new URL(url.pathname + url.search, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  return next();
});
