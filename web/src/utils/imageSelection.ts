import { proxyUrl } from '../lib/apiBase.ts';
import { isWeakVisual, scoreImageUrl } from '../lib/imageQuality.ts';

type ArticleLike = {
  image_url?: string | null;
  title?: string;
  category?: string;
  source?: string;
  topic?: string;
  description?: string;
};

type ClusterLike = {
  cluster_id?: string;
  representative_image?: string | null;
  articles?: ArticleLike[];
  topics?: string[];
  tags?: string[];
  synthetic_headline?: string | null;
  synthetic_standfirst?: string | null;
};

export type SiteLang = 'sr' | 'mk';
export type ImageVariant = 'hero' | 'card' | 'thumb';

const VARIANT_WIDTH: Record<ImageVariant, number> = {
  hero: 1200,
  card: 720,
  thumb: 320,
};

type FallbackKind = 'politics' | 'economy' | 'sport' | 'tech' | 'culture' | 'world' | 'local' | 'general';

function normalizeText(value?: string | null) {
  return String(value || '').toLowerCase();
}

function fallbackContext(cluster: ClusterLike) {
  const primary = cluster?.articles?.[0] || {};
  return {
    cid: cluster?.cluster_id || '',
    title: cluster?.synthetic_headline || primary.title || cluster?.synthetic_standfirst || '',
    category: primary.category || primary.topic || cluster?.topics?.[0] || cluster?.tags?.[0] || 'vesti',
  };
}

function getFallbackKind(cluster: ClusterLike): FallbackKind {
  const primary = cluster?.articles?.[0] || {};
  const haystack = [
    ...(cluster?.topics || []),
    ...(cluster?.tags || []),
    cluster?.synthetic_headline,
    cluster?.synthetic_standfirst,
    primary.topic,
    primary.category,
    primary.title,
    primary.description,
  ].map(normalizeText).join(' ');

  if (/(sport|fudbal|ko[šs]arka|tenis|liga|utakmica|gol|спорт|фудбал|кошарка|тенис|лига|натпревар|гол)/.test(haystack)) {
    return 'sport';
  }
  if (/(ekonom|biznis|finans|tr[žz]i[šs]te|inflaci|bud[žz]et|banka|берза|економ|бизнис|финанс|пазар|инфлаци|буџет|банка)/.test(haystack)) {
    return 'economy';
  }
  if (/(tehnolog|nauka|ai|softver|digital|cyber|sajber|startup|технолог|наука|софтвер|дигитал|сајбер|стартап)/.test(haystack)) {
    return 'tech';
  }
  if (/(kultur|umetnost|film|muzik|knjig|festival|театр|култур|уметност|филм|музик|книг|фестивал)/.test(haystack)) {
    return 'culture';
  }
  if (/(polit|vlada|sobran|parlament|izbor|opozici|ministar|premijer|predsed|полит|влада|собран|парламент|избор|опозици|министер|премиер|претсед)/.test(haystack)) {
    return 'politics';
  }
  if (/(svet|global|eu|nato|sad|amerika|rusija|ukraina|izrael|palestin|kina|европа|свет|глобал|сад|русија|украина|израел|палестин|кина)/.test(haystack)) {
    return 'world';
  }
  if (/(skopje|beograd|srbija|makedon|balkan|lokal|op[šs]tin|grad|скопје|белград|србија|македон|балкан|локал|општин|град)/.test(haystack)) {
    return 'local';
  }
  return 'general';
}

export function buildProxyUrlWithWidth(baseUrl: string, width: number): string {
  try {
    const url = new URL(baseUrl, 'https://presek.mk');
    url.searchParams.set('w', String(width));
    return `${url.pathname}${url.search}`;
  } catch {
    return baseUrl;
  }
}

export function buildProxySrcSet(baseUrl: string | null | undefined, widths: number[]): string {
  if (!baseUrl || widths.length === 0) return '';
  return widths.map((width) => `${buildProxyUrlWithWidth(baseUrl, width)} ${width}w`).join(', ');
}

export function buildProxyFallbackUrl(
  cluster: ClusterLike,
  lang: SiteLang = 'sr',
  variant: ImageVariant = 'card',
) {
  const context = fallbackContext(cluster);
  const params = new URLSearchParams();
  if (context.cid) params.set('cid', context.cid);
  if (context.title) params.set('t', context.title);
  if (context.category) params.set('cat', context.category);
  params.set('lang', lang);
  params.set('w', String(VARIANT_WIDTH[variant]));
  return proxyUrl(`/proxy?${params.toString()}`);
}

export function buildEmergencyFallbackUrl(lang: SiteLang = 'sr') {
  const params = new URLSearchParams({
    cat: lang === 'mk' ? 'вести' : 'vesti',
    lang,
    w: '720',
  });
  return proxyUrl(`/proxy?${params.toString()}`);
}

export function getFallbackImage(cluster: ClusterLike, lang: SiteLang = 'sr', variant: ImageVariant = 'card') {
  const kind = getFallbackKind(cluster);
  const smartSrc = buildProxyFallbackUrl(cluster, lang, variant);

  return {
    kind,
    src: smartSrc,
    smartSrc,
  };
}

function uniqueCandidates(cluster: ClusterLike) {
  const articles = cluster?.articles || [];
  const representativeSource = articles.find((article) => article.image_url === cluster?.representative_image)?.source;
  const seen = new Set<string>();
  const candidates: { url: string; source?: string }[] = [];

  for (const candidate of [
    { url: cluster?.representative_image, source: representativeSource },
    ...articles.map((article) => ({ url: article.image_url, source: article.source })),
  ]) {
    const url = String(candidate.url || '').trim();
    if (!url || seen.has(url)) continue;
    seen.add(url);
    candidates.push({ url, source: candidate.source });
  }

  return candidates;
}

export function chooseClusterImage(
  cluster: ClusterLike,
  variant: ImageVariant = 'card',
  lang: SiteLang = 'sr',
) {
  const candidates = uniqueCandidates(cluster);

  const ranked = candidates
    .map((candidate, index) => {
      const dimensions = extractImageDimensions(candidate.url);
      return {
        ...candidate,
        index,
        area: dimensions.width * dimensions.height,
        score: scoreImageUrl(candidate.url, candidate.source),
      };
    })
    .sort((a, b) => b.score - a.score || b.area - a.area || a.index - b.index);

  const chosen = ranked[0]?.url || '';
  const width = VARIANT_WIDTH[variant];
  const isWeak = isWeakVisual(chosen);
  const fallback = getFallbackImage(cluster, lang, variant);
  const context = fallbackContext(cluster);

  let proxiedUrl = null;
  if (chosen) {
    const params = new URLSearchParams({
      url: chosen,
      w: width.toString(),
      lang,
    });
    if (context.cid) params.set('cid', context.cid);
    if (context.title && variant !== 'hero') params.set('t', context.title);
    if (context.category) params.set('cat', context.category);
    proxiedUrl = proxyUrl(`/proxy?${params.toString()}`);
  }

  return {
    rawUrl: chosen || null,
    proxiedUrl: isWeak ? fallback.smartSrc : proxiedUrl,
    isWeak,
    fallbackUrl: fallback.smartSrc,
    /** @deprecated Use fallbackUrl — kept for callers that still read this field */
    staticFallbackUrl: fallback.smartSrc,
    fallbackKind: fallback.kind,
  };
}

function extractImageDimensions(url: string) {
  let parsed: URL | null = null;
  try {
    parsed = new URL(url, 'https://presek.mk');
  } catch {
    parsed = null;
  }

  const haystack = `${parsed?.pathname || ''} ${parsed?.search || ''} ${url}`.toLowerCase();
  const dimensionMatch = haystack.match(/(^|[^0-9])(\d{2,5})x(\d{2,5})([^0-9]|$)/);
  if (dimensionMatch) {
    return {
      width: Number(dimensionMatch[2]) || 0,
      height: Number(dimensionMatch[3]) || 0,
    };
  }

  return {
    width:
      Number(parsed?.searchParams.get('w')) ||
      Number(parsed?.searchParams.get('width')) ||
      Number(parsed?.searchParams.get('max_width')) ||
      0,
    height:
      Number(parsed?.searchParams.get('h')) ||
      Number(parsed?.searchParams.get('height')) ||
      Number(parsed?.searchParams.get('max_height')) ||
      0,
  };
}
