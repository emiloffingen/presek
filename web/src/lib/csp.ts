/** Per-request nonce for optional inline scripts (e.g. gtag bootstrap). */
export function generateCspNonce(): string {
  return crypto.randomUUID().replace(/-/g, '');
}

/** frame-ancestors must be set via HTTP header (ignored in meta CSP). */
export function buildFrameAncestorsPolicy(): string {
  return "frame-ancestors 'none'";
}

export function buildCspPolicy(): string {
  return (
    "default-src 'self'; " +
    "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; " +
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; " +
    "font-src 'self' data: https://fonts.gstatic.com; " +
    "img-src 'self' data: https: blob: https://www.google-analytics.com https://www.googletagmanager.com; " +
    "connect-src 'self' https://presek.live https://www.presek.live https://presek.mk https://www.presek.mk https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com https://region1.google-analytics.com wss://presek.live wss://presek.mk; " +
    "frame-src 'self'; " +
    "frame-ancestors 'none'; " +
    "base-uri 'self'; " +
    "form-action 'self'; " +
    "object-src 'none'; " +
    "media-src 'self' data: https:; " +
    "worker-src 'self' blob:"
  );
}
