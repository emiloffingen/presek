type ArticleLike = {
  image_url?: string | null;
  title?: string;
  category?: string;
  source?: string;
};

type ClusterLike = {
  cluster_id?: string;
  representative_image?: string | null;
  articles?: ArticleLike[];
};

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

export function chooseClusterImage(cluster: ClusterLike, variant: ImageVariant = 'card') {
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

  // Better fallback context for smart placeholders
  const cid = cluster?.cluster_id || '';
  const title = articles[0]?.title || '';
  const cat = articles[0]?.category || '';
  
  let proxiedUrl = null;
  if (chosen) {
    const params = new URLSearchParams({
      url: chosen,
      w: width.toString()
    });
    if (cid) params.set('cid', cid);
    if (title) params.set('t', title);
    if (cat) params.set('cat', cat);
    proxiedUrl = `/proxy?${params.toString()}`;
  }

  return {
    rawUrl: chosen || null,
    proxiedUrl,
    isWeak: isWeakVisual(chosen),
  };
}
