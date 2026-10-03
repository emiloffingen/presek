/**
 * Single source of truth for advertising prices.
 *
 * IMPORTANT: keep PROMO_DISCOUNT / CPM_BASE_EUR in sync with the backend in
 * routes/marketing.py (CPM_BASE_EUR, PROMO_DISCOUNT). The backend is the
 * authority for what is actually charged; this module only mirrors it for the
 * UI (booking form calculator, house-ad cards, price table).
 */

export type AdSlotId = 'top_banner' | 'sidebar' | 'mobile_content';

export type SiteLang = 'sr' | 'mk';

export const MKD_PER_EUR = 61.5;
export const RSD_PER_EUR = 117.0;

/**
 * Base CPM in EUR before the introductory promo. Benchmarked below MK news
 * rate cards (200-400 MKD) while staying defensible.
 */
export const CPM_BASE_EUR: Record<AdSlotId, number> = {
  top_banner: 2.44, // ~150 MKD
  sidebar: 2.93, // ~180 MKD
  mobile_content: 3.25, // ~200 MKD
};

/**
 * Introductory discount applied to every slot. Read at build time from
 * PUBLIC_PROMO_DISCOUNT (the build script derives it from PROMO_DISCOUNT in
 * .env) and kept in sync with the backend's runtime PROMO_DISCOUNT. Set to 0 to
 * remove the promo. Change via scripts/set_promo.sh so both sides stay aligned.
 */
function resolvePromoDiscount(): number {
  const env = (import.meta as { env?: Record<string, string | undefined> }).env;
  const raw = Number(env?.PUBLIC_PROMO_DISCOUNT);
  if (!Number.isFinite(raw)) return 0.25;
  return Math.min(Math.max(raw, 0), 0.95);
}

export const PROMO_DISCOUNT = resolvePromoDiscount();

const round4 = (value: number) => Math.round(value * 10000) / 10000;

/** Current (discounted) CPM actually charged, in EUR. */
export const CPM_RATES_EUR: Record<AdSlotId, number> = {
  top_banner: round4(CPM_BASE_EUR.top_banner * (1 - PROMO_DISCOUNT)),
  sidebar: round4(CPM_BASE_EUR.sidebar * (1 - PROMO_DISCOUNT)),
  mobile_content: round4(CPM_BASE_EUR.mobile_content * (1 - PROMO_DISCOUNT)),
};

export interface AdSlotMeta {
  /** Creative size hint shown to advertisers. */
  size: string;
  /** Minimum container height so the slot does not collapse while empty. */
  minHeight: string;
  /** Discounted EUR CPM. */
  eur: number;
  /** Pre-promo EUR CPM, for the struck-through comparison price. */
  baseEur: number;
}

const SLOT_BASE: Record<AdSlotId, Pick<AdSlotMeta, 'size' | 'minHeight'>> = {
  top_banner: { size: '990x80 / 990x150', minHeight: '120px' },
  sidebar: { size: '300x250 / 300x600', minHeight: '250px' },
  mobile_content: { size: '300x250', minHeight: '250px' },
};

export const SLOT_META: Record<AdSlotId, AdSlotMeta> = {
  top_banner: { ...SLOT_BASE.top_banner, eur: CPM_RATES_EUR.top_banner, baseEur: CPM_BASE_EUR.top_banner },
  sidebar: { ...SLOT_BASE.sidebar, eur: CPM_RATES_EUR.sidebar, baseEur: CPM_BASE_EUR.sidebar },
  mobile_content: { ...SLOT_BASE.mobile_content, eur: CPM_RATES_EUR.mobile_content, baseEur: CPM_BASE_EUR.mobile_content },
};

/** Convert a EUR CPM into the local currency amount per 1,000 impressions. */
export function localCpm(rateEur: number, lang: SiteLang): { amount: number; currency: 'MKD' | 'RSD' } {
  return lang === 'mk'
    ? { amount: Math.round(rateEur * MKD_PER_EUR), currency: 'MKD' }
    : { amount: Math.round(rateEur * RSD_PER_EUR), currency: 'RSD' };
}

/** Discount as a whole percentage, e.g. 25. */
export const PROMO_PERCENT = Math.round(PROMO_DISCOUNT * 100);
