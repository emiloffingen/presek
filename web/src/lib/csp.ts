export function generateCspNonce(): string {
  return crypto.randomUUID().replace(/-/g, '');
}

export function buildContentSecurityPolicy(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' https://www.googletagmanager.com`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    "img-src 'self' data: https: blob: https://www.google-analytics.com https://www.googletagmanager.com",
    "connect-src 'self' https: wss: https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com",
    "frame-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "media-src 'self' data: https:",
    "worker-src 'self'",
  ].join('; ');
}
