export type TrustTier = 'early' | 'consensus' | 'plural' | 'verified';

export type TrustChipData = {
  score: number;
  tier: TrustTier;
  label: string;
  detail: string;
  sourcesCount: number;
  pluralismScore?: number | null;
  isStale?: boolean;
  isProvisional?: boolean;
};

type TrustInput = {
  sourcesCount: number;
  pluralismScore?: number | null;
  isStale?: boolean;
  hasVerification?: boolean;
  /** When true, omit "synthesis updating" notes (feed cards, pending synthesis). */
  quietFreshness?: boolean;
  /** First-time synthesis not written yet. */
  isPendingSynthesis?: boolean;
  /** Fast-mode or fallback synthesis awaiting full upgrade. */
  isProvisional?: boolean;
  needsUpgrade?: boolean;
};

export function buildTrustChip(input: TrustInput, lang: 'sr' | 'mk'): TrustChipData {
  const sources = Math.max(0, input.sourcesCount || 0);
  const pluralism = input.pluralismScore ?? null;
  const pluralismVal = pluralism == null ? 0 : Number(pluralism);
  const isStale = Boolean(input.isStale);
  const hasVerification = Boolean(input.hasVerification);
  const isPendingSynthesis = Boolean(input.isPendingSynthesis);
  const isProvisional = Boolean(input.isProvisional || input.needsUpgrade);

  let tier: TrustTier = 'verified';
  let label = lang === 'mk' ? 'Проверено' : 'Provereno';
  let detail =
    lang === 'mk'
      ? `${sources} независни извори се следат.`
      : `${sources} nezavisna izvora se prate.`;

  if (isProvisional && sources >= 2) {
    tier = 'early';
    label = lang === 'mk' ? 'Привремен преглед' : 'Privremeni pregled';
    detail =
      lang === 'mk'
        ? 'Првичен преглед — целосната синтеза се надградува.'
        : 'Prvični pregled — puna sinteza se nadograđuje.';
  } else if (isPendingSynthesis && sources >= 2) {
    tier = 'early';
    label = lang === 'mk' ? 'Се подготвува' : 'U pripremi';
    detail =
      lang === 'mk'
        ? `${sources} извори се поврзани; уредничкиот преглед се генерира.`
        : `${sources} izvora je povezano; urednički pregled se generiše.`;
  } else if (sources < 2) {
    tier = 'early';
    label = lang === 'mk' ? 'Ран сигнал' : 'Rani signal';
    detail =
      lang === 'mk'
        ? 'Сè уште една редакција — третирајте го како почетен извештај.'
        : 'Još jedna redakcija — tretirajte kao početni izveštaj.';
  } else if (pluralismVal >= 55) {
    tier = 'plural';
    label = lang === 'mk' ? 'Плурализам' : 'Pluralizam';
    detail =
      lang === 'mk'
        ? `${sources} извори, различни нагласи (${pluralismVal}%).`
        : `${sources} izvora, različiti naglasci (${pluralismVal}%).`;
  } else if (pluralismVal <= 15) {
    tier = 'consensus';
    label = lang === 'mk' ? 'Консензус' : 'Konsenzus';
    detail =
      lang === 'mk'
        ? `${sources} извори покриваат иста приказна.`
        : `${sources} izvora pokrivaju istu priču.`;
  }

  if (isStale && !input.quietFreshness) {
    detail =
      lang === 'mk'
        ? `${detail} Синтезата се освежува.`
        : `${detail} Sinteza se osvežava.`;
  }

  const score = Math.min(
    100,
    Math.max(
      0,
      Math.min(sources, 8) * 10 +
        (pluralismVal <= 15 ? 25 : pluralismVal >= 55 ? 12 : 18) +
        (isStale || isProvisional ? 0 : 20) +
        (hasVerification ? 10 : 0),
    ),
  );

  return {
    score,
    tier,
    label,
    detail,
    sourcesCount: sources,
    pluralismScore: pluralism,
    isStale,
    isProvisional,
  };
}

function sourcesShortLabel(count: number, lang: 'sr' | 'mk'): string {
  if (lang === 'mk') {
    return count === 1 ? '1 извор' : `${count} изв.`;
  }
  return count === 1 ? '1 izvor' : `${count} izv.`;
}

/** Single-line trust badge for feed cards (replaces TrustChip + signal row + footer meta). */
export function buildPrimaryCardBadge(input: TrustInput, lang: 'sr' | 'mk'): string {
  const sources = Math.max(0, input.sourcesCount || 0);
  const sourcesLabel = sourcesShortLabel(sources, lang);
  const trust = buildTrustChip({ ...input, quietFreshness: true }, lang);

  if (trust.tier === 'consensus') {
    return lang === 'mk' ? `Консензус · ${sourcesLabel}` : `Konsenzus · ${sourcesLabel}`;
  }

  if (trust.tier === 'plural') {
    const pct = input.pluralismScore ?? '';
    const pluralLabel = lang === 'mk' ? 'Различни агли' : 'Različiti uglovi';
    return pct !== '' && pct != null
      ? `${pluralLabel} · ${sourcesLabel} · ${pct}%`
      : `${pluralLabel} · ${sourcesLabel}`;
  }

  return `${trust.label} · ${sourcesLabel}`;
}

export function primaryCardBadgeTier(input: TrustInput): TrustTier {
  return buildTrustChip({ ...input, quietFreshness: true }, 'sr').tier;
}

/** Short footer label for compact/wire cards where TrustChip row is hidden. */
export function buildCompactPluralismMeta(input: TrustInput, lang: 'sr' | 'mk'): string | null {
  if ((input.sourcesCount || 0) < 1) {
    return null;
  }

  return buildPrimaryCardBadge(input, lang);
}
