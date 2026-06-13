export const HILLTOPADS_VERIFICATION_TOKEN_LIVE = 'a3a999fcaa2f5ffa9e13b1e2489c2488ac0bfba3';
export const HILLTOPADS_VERIFICATION_TOKEN_MK = 'd07d1cfa2d1d864d0e56d9b80842c7dde3a1d1a8';

/** @deprecated Use hilltopAdsVerificationToken(hostname). */
export const HILLTOPADS_VERIFICATION_TOKEN = HILLTOPADS_VERIFICATION_TOKEN_LIVE;

/** MultiTag Banner 300×250 invoker (legacy; includes banner + popunder). */
export const HILLTOPADS_MULTITAG_BANNER_INVOKER_SRC =
  '//conventionalresponse.com/bXX.V/sSdEGrlX0kYkWvcY/SekmC9ZurZpU/l-k/P/TscMxKMOzjQr0wMDTEcWtONZz/EkzXNZDtQRydMdQk';

/** MultiTag In-Page invoker (presek.live zone from HilltopAds dashboard). */
export const HILLTOPADS_MULTITAG_INPAGE_INVOKER_SRC =
  '//conventionalresponse.com/bWXdVfs.duGmlX0/YIW/cG/delmy9fu_ZIUslok_PbTAcpx/M/zwQP0JNMT/cAtFNdzZETzYNRDeQc2WMjQz';

export type HilltopZone = 'popunder' | 'inpage' | 'multitag' | 'multitag-inpage';

const ZONE_ENV_SRC: Record<HilltopZone, string> = {
  popunder: 'PUBLIC_HILLTOPADS_POPUNDER_SRC',
  inpage: 'PUBLIC_HILLTOPADS_INPAGE_SRC',
  multitag: 'PUBLIC_HILLTOPADS_MULTITAG_SRC',
  'multitag-inpage': 'PUBLIC_HILLTOPADS_MULTITAG_INPAGE_SRC',
};

const ZONE_ENV_ENABLED: Record<HilltopZone, string> = {
  popunder: 'PUBLIC_HILLTOPADS_POPUNDER_ENABLED',
  inpage: 'PUBLIC_HILLTOPADS_INPAGE_ENABLED',
  multitag: 'PUBLIC_HILLTOPADS_MULTITAG_ENABLED',
  'multitag-inpage': 'PUBLIC_HILLTOPADS_MULTITAG_INPAGE_ENABLED',
};

const ZONE_DEFAULT_SRC: Partial<Record<HilltopZone, string>> = {
  multitag: HILLTOPADS_MULTITAG_BANNER_INVOKER_SRC,
  'multitag-inpage': HILLTOPADS_MULTITAG_INPAGE_INVOKER_SRC,
};

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

function isMkHost(host: string): boolean {
  return host === 'presek.mk' || host === 'www.presek.mk';
}

function parseEnabledFlag(raw: string, defaultValue: boolean): boolean {
  if (raw === 'true' || raw === '1') return true;
  if (raw === 'false' || raw === '0') return false;
  return defaultValue;
}

export function hilltopAdsDisabled(): boolean {
  const raw = readEnv('PUBLIC_HILLTOPADS_ENABLED').toLowerCase();
  return raw === 'false' || raw === '0';
}

/** Site-wide HilltopAds on presek.live (Serbian edition). */
export function shouldLoadHilltopAds(lang: 'sr' | 'mk', hostname: string): boolean {
  if (hilltopAdsDisabled()) return false;
  const host = normalizeHost(hostname);
  return lang === 'sr' && isLiveHost(host);
}

export function hilltopAdsVerificationToken(hostname: string): string | null {
  const host = normalizeHost(hostname);
  if (isLiveHost(host)) return HILLTOPADS_VERIFICATION_TOKEN_LIVE;
  if (isMkHost(host)) return HILLTOPADS_VERIFICATION_TOKEN_MK;
  return null;
}

export function shouldShowHilltopAdsVerification(hostname: string): boolean {
  return hilltopAdsVerificationToken(hostname) !== null;
}

export function hilltopZoneInvokerSrc(zone: HilltopZone): string {
  const fromEnv = readEnv(ZONE_ENV_SRC[zone]);
  if (fromEnv) return fromEnv;
  return ZONE_DEFAULT_SRC[zone] || '';
}

export function isHilltopZoneEnabled(zone: HilltopZone): boolean {
  const raw = readEnv(ZONE_ENV_ENABLED[zone]);
  const defaultEnabled = zone === 'multitag-inpage';
  return parseEnabledFlag(raw, defaultEnabled);
}

export function listActiveHilltopZones(): HilltopZone[] {
  return (['multitag-inpage', 'inpage', 'multitag', 'popunder'] as const).filter(
    (zone) => isHilltopZoneEnabled(zone) && Boolean(hilltopZoneInvokerSrc(zone)),
  );
}

/** @deprecated Use hilltopZoneInvokerSrc('multitag'). */
export function hilltopMultitagInvokerSrc(): string {
  return hilltopZoneInvokerSrc('multitag');
}
