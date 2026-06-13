function readEnv(name: string): string {
  const fromProcess =
    typeof process !== 'undefined' ? process.env[name]?.trim() : '';
  const fromImport = String(import.meta.env[name] || '').trim();
  return fromProcess || fromImport;
}

function normalizeHost(hostname: string): string {
  return hostname.split(':')[0].toLowerCase();
}

function isLiveHost(host: string): boolean {
  return host === 'presek.live' || host === 'www.presek.live';
}

/** Google AdSense on presek.live (Serbian edition). Disable via PUBLIC_ADSENSE_ENABLED=false. */
export function shouldLoadAdsense(lang: 'sr' | 'mk', hostname: string): boolean {
  const raw = readEnv('PUBLIC_ADSENSE_ENABLED').toLowerCase();
  if (raw === 'false' || raw === '0') return false;
  const host = normalizeHost(hostname);
  return lang === 'sr' && isLiveHost(host);
}
