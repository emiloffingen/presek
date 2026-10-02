import { createHash } from 'node:crypto';

/** Per-request nonce for optional inline scripts (e.g. gtag bootstrap). */
export function generateCspNonce(): string {
  return crypto.randomUUID().replace(/-/g, '');
}

/** frame-ancestors must be set via HTTP header (ignored in meta CSP). */
export function buildFrameAncestorsPolicy(): string {
  return "frame-ancestors 'none'";
}

export interface CspHashes {
  scripts: string[];
  styles: string[];
}

/**
 * Compute `'sha256-...'` CSP hashes for inline `<script>` and `<style>` blocks
 * that were emitted without a nonce (e.g. Astro's `astro-island` definition,
 * client-directive bootstraps, and Astro component scoped styles). Without
 * these hashes the browser blocks the inline content under our nonce-only CSP,
 * which prevents `astro-island` from being registered as a custom element —
 * and therefore prevents every React island (search overlay, theme toggle,
 * text-scale, etc.) from hydrating.
 */
export function computeInlineHashes(html: string, { includeNonced = false } = {}): CspHashes {
  const scripts: string[] = [];
  const styles: string[] = [];
  const hash = (content: string): string => {
    const digest = createHash('sha256').update(content, 'utf8').digest('base64');
    return `'sha256-${digest}'`;
  };

  for (const match of html.matchAll(/<script\b([^>]*?)>([\s\S]*?)<\/script>/gi)) {
    const attrs = match[1] || '';
    const body = match[2] || '';
    if (!includeNonced && /\snonce\s*=/.test(attrs)) continue;
    if (/\ssrc\s*=/.test(attrs)) continue;
    if (!body.trim()) continue;
    if (/type\s*=\s*["']application\/ld\+json["']/.test(attrs)) continue;
    scripts.push(hash(body));
  }

  // style-src uses 'unsafe-inline' with no nonce/hash (see buildCspPolicy), so
  // style hashes are never consumed — skip the work of computing them.
  return { scripts, styles };
}

export function buildCspPolicy(nonce: string | null, hashes: CspHashes = { scripts: [], styles: [] }): string {
  const scriptHashes = hashes.scripts.length ? ' ' + hashes.scripts.join(' ') : '';
  const nonceSource = nonce ? ` 'nonce-${nonce}'` : '';
  return (
    "default-src 'self'; " +
    `script-src 'self'${nonceSource}${scriptHashes} https://www.googletagmanager.com; ` +
    // style-src deliberately uses 'unsafe-inline' with NO nonce/hash: a nonce or
    // hash in a source list makes browsers ignore 'unsafe-inline'. Astro's island
    // runtime and React set inline `style` attributes, and style attributes can
    // never be authorised by nonce/hash (only by 'unsafe-hashes' + the exact
    // value). Without this, hydration silently aborts and every island is inert.
    // Script execution stays locked to nonce + hashes.
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
