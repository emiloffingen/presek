import { buildTrustChip } from './trustSignals.ts';

export type EmbedTrustLabels = {
  unavailable: string;
  kicker: string;
  footerHost: string;
};

export function buildEmbedTrustLabels(lang: 'sr' | 'mk'): EmbedTrustLabels {
  if (lang === 'mk') {
    return {
      unavailable: 'Кластерот не е достапен.',
      kicker: 'Сигнал на доверба',
      footerHost: 'presek.mk',
    };
  }
  return {
    unavailable: 'Klaster nije dostupan.',
    kicker: 'Signal poverenja',
    footerHost: 'presek.live',
  };
}

export function resolveEmbedTrustLang(
  langParam: string | null | undefined,
  hostHeader: string,
): 'sr' | 'mk' {
  if (langParam === 'mk') return 'mk';
  if (langParam === 'sr') return 'sr';
  return hostHeader.includes('presek.mk') ? 'mk' : 'sr';
}

export function buildEmbedClusterUrl(clusterId: string, lang: 'sr' | 'mk') {
  const host = lang === 'mk' ? 'presek.mk' : 'presek.live';
  return `https://${host}/cluster/${clusterId}`;
}

export async function loadEmbedTrustData({
  apiUrl,
  clusterId,
  lang,
  fetchJson,
}: {
  apiUrl: string;
  clusterId: string;
  lang: 'sr' | 'mk';
  fetchJson: (url: string) => Promise<any>;
}) {
  if (!clusterId) {
    return { cluster: null, error: 'missing cluster id' };
  }

  try {
    const cluster = await fetchJson(`${apiUrl}/cluster/${clusterId}?lang=${lang}`);
    return { cluster, error: null };
  } catch (err: any) {
    return { cluster: null, error: err?.message || 'fetch failed' };
  }
}

export function buildEmbedTrustViewModel(cluster: any, lang: 'sr' | 'mk', clusterId: string) {
  const labels = buildEmbedTrustLabels(lang);
  const trustApi = cluster?.trust_summary;
  const sourcesCount =
    trustApi?.sources_count ??
    new Set((cluster?.articles || []).map((article: any) => article?.source).filter(Boolean)).size;

  const trust = buildTrustChip(
    {
      sourcesCount,
      pluralismScore: trustApi?.pluralism_score ?? cluster?.pluralism_score,
      isStale: Boolean(trustApi?.is_stale),
      hasVerification: Boolean(trustApi?.has_verification || cluster?.has_fact_check),
      isProvisional: Boolean(trustApi?.is_provisional || cluster?.synthesis_meta?.is_provisional),
      needsUpgrade: Boolean(trustApi?.needs_upgrade || cluster?.synthesis_meta?.needs_upgrade),
    },
    lang,
  );

  const headline = cluster?.synthetic_headline || cluster?.articles?.[0]?.title || 'Presek';
  const detail = trustApi?.detail || trust.detail;

  return {
    labels,
    headline,
    detail,
    clusterUrl: buildEmbedClusterUrl(clusterId, lang),
    trustChip: {
      sourcesCount,
      pluralismScore: trust.pluralismScore,
      isStale: trust.isStale,
      hasVerification: Boolean(trustApi?.has_verification || cluster?.has_fact_check),
      isProvisional: Boolean(trustApi?.is_provisional || cluster?.synthesis_meta?.is_provisional),
      needsUpgrade: Boolean(trustApi?.needs_upgrade || cluster?.synthesis_meta?.needs_upgrade),
    },
    trustSummary: trust,
  };
}
