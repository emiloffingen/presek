export const TINYADZ_SCRIPT_URL = 'https://cdn.apitiny.net/scripts/v2.0/main.js';
export const TINYADZ_DEFAULT_SITE_ID = '6a2995c32b7233c34b097a9c';

function readEnv(name: string): string {
  const fromProcess =
    typeof process !== 'undefined' ? process.env[name]?.trim() : '';
  const fromImport = String(import.meta.env[name] || '').trim();
  return fromProcess || fromImport;
}

export function tinyAdzSiteId(): string {
  return readEnv('PUBLIC_TINYADZ_SITE_ID') || TINYADZ_DEFAULT_SITE_ID;
}

export function tinyAdzTestMode(): boolean {
  const raw = readEnv('PUBLIC_TINYADZ_TEST_MODE').toLowerCase();
  return raw === 'true' || raw === '1';
}

export function shouldLoadTinyAdz(lang: 'sr' | 'mk', hostname: string): boolean {
  if (lang !== 'mk') {
    return false;
  }

  const host = hostname.split(':')[0].toLowerCase();
  return host === 'presek.mk' || host === 'www.presek.mk';
}
