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
  '/static/generated/',
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
  'screenshot',
  'thumb',
  'thumbnail',
  'small',
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
  if (value.length < 15) return true; // Too short to be a real CDN URL usually
  return WEAK_VISUAL_TOKENS.some((token) => value.includes(token));
}

function scoreImage(url: string, source?: string): number {
  let score = 10;
  if (isWeakVisual(url)) score -= 8;
  
  const val = url.toLowerCase();
  // Prefer JPG/WEBP over PNG (usually photos vs logos)
  if (val.includes('.jpg') || val.includes('.jpeg')) score += 2;
  if (val.includes('.webp')) score += 2;
  if (val.includes('.png')) score -= 1;

  // CDNs often have higher quality images than direct uploads
  if (val.includes('cdn') || val.includes('imgix') || val.includes('cloudinary')) score += 1;
  
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
  
  const candidates = [
    { url: cluster?.representative_image, source: articles[0]?.source },
    ...articles.map(a => ({ url: a.image_url, source: a.source }))
  ].filter(c => !!c.url) as { url: string, source: string }[];

  // Rank candidates
  const ranked = candidates
    .map(c => ({ ...c, score: scoreImage(c.url, c.source) }))
    .sort((a, b) => b.score - a.score);

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
