import { defineMiddleware } from 'astro:middleware';

export const onRequest = defineMiddleware((context, next) => {
  const url = new URL(context.request.url);
  const host = context.request.headers.get('host') || url.hostname;
  const hostname = host.split(':')[0].toLowerCase();

  // Redirect presek.live/mk/* to presek.mk/*
  if ((hostname === 'presek.live' || hostname === 'www.presek.live') && url.pathname.startsWith('/mk')) {
    const targetPath = url.pathname.replace(/^\/mk/, '') || '/';
    const target = new URL(targetPath + url.search, 'https://presek.mk');
    return Response.redirect(target, 301);
  }

  // Redirect presek.mk/sr/* to presek.live/*
  if ((hostname === 'presek.mk' || hostname === 'www.presek.mk') && url.pathname.startsWith('/sr')) {
    const targetPath = url.pathname.replace(/^\/sr/, '') || '/';
    const target = new URL(targetPath + url.search, 'https://presek.live');
    return Response.redirect(target, 301);
  }

  return next();
});
