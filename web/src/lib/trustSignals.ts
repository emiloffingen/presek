import { cluster } from '../i18n/namespaces/cluster.ts';

type Lang = 'sr' | 'mk';

function trustT(lang: Lang, key: string, params?: Record<string, string | number>): string {
  const dict = (cluster[lang] || cluster.mk) as Record<string, string>;
  let value = dict[key] ?? key;
  if (params) {
    for (const [paramKey, paramValue] of Object.entries(params)) {
      value = value.replaceAll(`{${paramKey}}`, String(paramValue));
    }
  }
  return value;
}

export type TrustTier = 'early' | 'consensus' | 'plural' | 'verified';

export type TrustBreakdownKey = 'sources' | 'pluralism' | 'freshness' | 'verification';

export type TrustBreakdownItem = {
  key: TrustBreakdownKey;
  label: string;
  /** Points this factor contributed to the (capped) score. */
  points: number;
  /** Maximum points this factor can contribute. */
  max: number;
};

export type TrustChipData = {
  score: number;
  tier: TrustTier;
  label: string;
  detail: string;
  sourcesCount: number;
  pluralismScore?: number | null;
  isStale?: boolean;
  isProvisional?: boolean;
  /** How the score was computed, one entry per contributing factor. */
  breakdown: TrustBreakdownItem[];
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

export function buildTrustChip(input: TrustInput, lang: Lang): TrustChipData {
  const sources = Math.max(0, input.sourcesCount || 0);
  const pluralism = input.pluralismScore ?? null;
  const pluralismVal = pluralism == null ? 0 : Number(pluralism);
  const isStale = Boolean(input.isStale);
  const hasVerification = Boolean(input.hasVerification);
  const isPendingSynthesis = Boolean(input.isPendingSynthesis);
  const isProvisional = Boolean(input.isProvisional || input.needsUpgrade);

  let tier: TrustTier = 'verified';
  let label = trustT(lang, 'trust.chip.verified');
  let detail = trustT(lang, 'trust.chip.verified_detail', { count: sources });

  if (isProvisional && sources >= 2) {
    tier = 'early';
    label = trustT(lang, 'trust.chip.provisional');
    detail = trustT(lang, 'trust.chip.provisional_detail');
  } else if (isPendingSynthesis && sources >= 2) {
    tier = 'early';
    label = trustT(lang, 'trust.chip.pending');
    detail = trustT(lang, 'trust.chip.pending_detail', { count: sources });
  } else if (sources < 2) {
    tier = 'early';
    label = trustT(lang, 'trust.chip.early');
    detail = trustT(lang, 'trust.chip.early_detail');
  } else if (pluralismVal >= 55) {
    tier = 'plural';
    label = trustT(lang, 'trust.chip.plural');
    detail = trustT(lang, 'trust.chip.plural_detail', { count: sources, score: pluralismVal });
  } else if (pluralismVal <= 15) {
    tier = 'consensus';
    label = trustT(lang, 'trust.chip.consensus');
    detail = trustT(lang, 'trust.chip.consensus_detail', { count: sources });
  }

  if (isStale && !input.quietFreshness) {
    detail = `${detail} ${trustT(lang, 'trust.stale')}`;
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

  const breakdown: TrustBreakdownItem[] = [
    {
      key: 'sources',
      label: trustT(lang, 'trust.breakdown_sources'),
      points: Math.min(sources, 8) * 10,
      max: 80,
    },
    {
      key: 'pluralism',
      label: trustT(lang, 'trust.breakdown_pluralism'),
      points: pluralismVal <= 15 ? 25 : pluralismVal >= 55 ? 12 : 18,
      max: 25,
    },
    {
      key: 'freshness',
      label: trustT(lang, 'trust.breakdown_freshness'),
      points: isStale || isProvisional ? 0 : 20,
      max: 20,
    },
    {
      key: 'verification',
      label: trustT(lang, 'trust.breakdown_verification'),
      points: hasVerification ? 10 : 0,
      max: 10,
    },
  ];

  return {
    score,
    tier,
    label,
    detail,
    sourcesCount: sources,
    pluralismScore: pluralism,
    isStale,
    isProvisional,
    breakdown,
  };
}

function sourcesShortLabel(count: number, lang: Lang): string {
  if (count === 1) {
    return trustT(lang, 'trust.source_one');
  }
  return trustT(lang, 'trust.source_abbr', { count });
}

/** Single-line trust badge for feed cards (replaces TrustChip + signal row + footer meta). */
export function buildPrimaryCardBadge(input: TrustInput, lang: Lang): string {
  const sources = Math.max(0, input.sourcesCount || 0);
  const sourcesLabel = sourcesShortLabel(sources, lang);
  const trust = buildTrustChip({ ...input, quietFreshness: true }, lang);

  if (trust.tier === 'consensus') {
    return trustT(lang, 'trust.badge.consensus', { sources: sourcesLabel });
  }

  if (trust.tier === 'plural') {
    const pct = input.pluralismScore ?? '';
    const pluralLabel = trustT(lang, 'trust.badge.plural_angles');
    return pct !== '' && pct != null
      ? `${pluralLabel} · ${sourcesLabel} · ${pct}%`
      : `${pluralLabel} · ${sourcesLabel}`;
  }

  return `${trust.label} · ${sourcesLabel}`;
}

export function primaryCardBadgeTier(input: TrustInput): TrustTier {
  return buildTrustChip({ ...input, quietFreshness: true }, 'mk').tier;
}

/** Short footer label for compact/wire cards where TrustChip row is hidden. */
export function buildCompactPluralismMeta(input: TrustInput, lang: Lang): string | null {
  if ((input.sourcesCount || 0) < 1) {
    return null;
  }

  return buildPrimaryCardBadge(input, lang);
}
