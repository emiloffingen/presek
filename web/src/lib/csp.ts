/** Per-request nonce for optional inline scripts (e.g. gtag bootstrap). */
export function generateCspNonce(): string {
  return crypto.randomUUID().replace(/-/g, '');
}

/** frame-ancestors must be set via HTTP header (ignored in meta CSP). */
export function buildFrameAncestorsPolicy(): string {
  return "frame-ancestors 'none'";
}
