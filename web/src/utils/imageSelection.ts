import { proxyUrl } from '../lib/apiBase.ts';

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

const WEAK_VISUAL_TOKENS = [
  '.svg',
  'placeholder',
  'default',
  'logo',
  'emblem',
  'avatar',
  'icon',
  'watermark',
  'republika',
  'online',
  'banner',
  'sprite',
  'facebook-share',
  'twitter-share',
  'social-default',
  'fallback',
  'no-image',
  'img-missing',
  'bez-slika',
  'naslovna',
  'logo-fixed',
  'breaking-news-generic',
];

export function isWeakVisual(url?: string | null) {
  const value = String(url || '').toLowerCase().trim();
  if (!value) return true;
  // Generated AI art is never weak
  if (value.includes('/static/generated/')) return false;
  if (value.length < 15) return true;
  return WEAK_VISUAL_TOKENS.some((token) => value.includes(token));
}

function tryParseUrl(url: string) {
  try {
    return new URL(url, 'https://presek.mk');
  } catch {
    return null;
  }
}

function extractImageDimensions(url: string) {
  const parsed = tryParseUrl(url);
  const haystack = `${parsed?.pathname || ''} ${parsed?.search || ''} ${url}`.toLowerCase();

  const dimensionMatch = haystack.match(/(^|[^0-9])(\d{2,5})x(\d{2,5})([^0-9]|$)/);
  if (dimensionMatch) {
    return {
      width: Number(dimensionMatch[2]) || 0,
      height: Number(dimensionMatch[3]) || 0,
    };
  }

  const width =
    Number(parsed?.searchParams.get('w')) ||
    Number(parsed?.searchParams.get('width')) ||
    Number(parsed?.searchParams.get('max_width')) ||
    0;
  const height =
    Number(parsed?.searchParams.get('h')) ||
    Number(parsed?.searchParams.get('height')) ||
    Number(parsed?.searchParams.get('max_height')) ||
    0;

  return { width, height };
}

function scoreImage(url: string, source?: string): number {
  let score = 0;
  const val = url.toLowerCase();
  const { width, height } = extractImageDimensions(url);
  const area = width * height;

  if (isWeakVisual(url)) score -= 12;

  // Prefer JPG/WEBP over PNG (usually photos vs logos)
  if (val.includes('.avif')) score += 3;
  if (val.includes('.jpg') || val.includes('.jpeg')) score += 2;
  if (val.includes('.webp')) score += 2;
  if (val.includes('.png')) score -= 1;

  // CDNs often have higher quality images than direct uploads
  if (val.includes('cdn') || val.includes('imgix') || val.includes('cloudinary')) score += 1;

  if (area) score += Math.min(area / 240000, 10);
  if (width >= 1400 || height >= 1400) score += 4;
  else if (width >= 1000 || height >= 1000) score += 2.5;
  else if (width >= 700 || height >= 700) score += 1.25;
  if (width && width < 180) score -= 6;
  if (height && height < 180) score -= 6;

  if (/(thumb|thumbnail|sprite|logo|icon|avatar|favicon|pixel|small)/.test(val)) score -= 7;
  if (/(hero|lead|main|large|full|original)/.test(val)) score += 2;

  // High-quality source bonus
  const highQualSources = ['sdk', '360stepeni', 'prizma', 'slobodnaevropa', 'dw'];
  if (source && highQualSources.some(s => source.toLowerCase().includes(s))) {
    score += 2;
  }

  return score;
}

type ImageVariant = 'hero' | 'card' | 'thumb';

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

export function chooseClusterImage(
  cluster: ClusterLike,
  variant: ImageVariant = 'card',
  lang: SiteLang = 'sr',
) {
  const articles = cluster?.articles || [];
  const representativeSource = articles.find((article) => article.image_url === cluster?.representative_image)?.source;

  const candidates = [
    { url: cluster?.representative_image, source: representativeSource },
    ...articles.map(a => ({ url: a.image_url, source: a.source }))
  ].filter(c => !!c.url) as { url: string, source: string }[];

  // Rank candidates
  const ranked = candidates
    .map((c, index) => {
      const dimensions = extractImageDimensions(c.url);
      return {
        ...c,
        index,
        area: dimensions.width * dimensions.height,
        score: scoreImage(c.url, c.source),
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
    if (context.title) params.set('t', context.title);
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
