export const TINYADZ_SCRIPT_URL = 'https://cdn.apitiny.net/scripts/v2.0/main.js';
export const TINYADZ_MK_SITE_ID = '6a2995c32b7233c34b097a9c';
export const TINYADZ_LIVE_SITE_ID = '6a29a71de09ffcc4c9bbd83e';

/** Premium reader surfaces stay ad-free. */
export const PREMIUM_AD_FREE_PATHS = new Set([
  '/for-you',
  '/settings',
  '/briefing',
  '/mk/for-you',
  '/mk/settings',
  '/mk/briefing',
]);

function readEnv(name: string): string {
  const fromProcess =
    typeof process !== 'undefined' ? process.env[name]?.trim() : '';
  const fromImport = String(import.meta.env[name] || '').trim();
  return fromProcess || fromImport;
}

function normalizeHost(hostname: string): string {
  return hostname.split(':')[0].toLowerCase();
}

function normalizePath(pathname: string): string {
  const trimmed = (pathname || '/').replace(/\/$/, '');
  return trimmed || '/';
}

function isMkHost(host: string): boolean {
  return host === 'presek.mk' || host === 'www.presek.mk';
}

function isLiveHost(host: string): boolean {
  return host === 'presek.live' || host === 'www.presek.live';
}

export function isPremiumAdFreePage(pathname: string): boolean {
  return PREMIUM_AD_FREE_PATHS.has(normalizePath(pathname));
}

export function shouldLoadTinyAdzScript(lang: 'sr' | 'mk', hostname: string): boolean {
  const host = normalizeHost(hostname);
  if (lang === 'mk' && isMkHost(host)) {
    return true;
  }
  if (lang === 'sr' && isLiveHost(host)) {
    return true;
  }
  return false;
}

/** Inlined `<div ta-ad-container>` slots on presek.mk and presek.live. */
export function shouldShowTinyAdzInlinedAds(
  lang: 'sr' | 'mk',
  hostname: string,
  pathname = '',
): boolean {
  if (pathname && isPremiumAdFreePage(pathname)) {
    return false;
  }
  return shouldLoadTinyAdzScript(lang, hostname);
}

/** @deprecated Use shouldLoadTinyAdzScript or shouldShowTinyAdzInlinedAds. */
export function shouldLoadTinyAdz(lang: 'sr' | 'mk', hostname: string): boolean {
  return shouldLoadTinyAdzScript(lang, hostname);
}

export function tinyAdzSiteId(lang: 'sr' | 'mk', hostname: string): string {
  const host = normalizeHost(hostname);
  if (lang === 'sr' && isLiveHost(host)) {
    return readEnv('PUBLIC_TINYADZ_LIVE_SITE_ID') || TINYADZ_LIVE_SITE_ID;
  }
  return readEnv('PUBLIC_TINYADZ_SITE_ID') || readEnv('PUBLIC_TINYADZ_MK_SITE_ID') || TINYADZ_MK_SITE_ID;
}

export function tinyAdzTestMode(): boolean {
  const raw = readEnv('PUBLIC_TINYADZ_TEST_MODE').toLowerCase();
  return raw === 'true' || raw === '1';
}
