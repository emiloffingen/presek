type ArticleLike = {
  image_url?: string | null;
  title?: string;
  category?: string;
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
];

export function isWeakVisual(url?: string | null) {
  const value = String(url || '').toLowerCase().trim();
  if (!value) return true;
  return WEAK_VISUAL_TOKENS.some((token) => value.includes(token));
}

type ImageVariant = 'hero' | 'card' | 'thumb';

const VARIANT_WIDTH: Record<ImageVariant, number> = {
  hero: 1200,
  card: 720,
  thumb: 320,
};

export function chooseClusterImage(cluster: ClusterLike, variant: ImageVariant = 'card') {
  const candidates = [
    cluster?.representative_image,
    cluster?.articles?.[0]?.image_url,
    ...((cluster?.articles || []).map((article) => article?.image_url)),
  ].filter(Boolean) as string[];

  const preferred = candidates.find((candidate) => !isWeakVisual(candidate));
  const chosen = preferred || candidates[0] || '';
  const width = VARIANT_WIDTH[variant];

  // Better fallback context for smart placeholders
  const cid = cluster?.cluster_id || '';
  const title = cluster?.articles?.[0]?.title || '';
  const cat = cluster?.articles?.[0]?.category || '';
  
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
