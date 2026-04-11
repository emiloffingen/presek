type ArticleLike = {
  image_url?: string | null;
};

type ClusterLike = {
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

  return {
    rawUrl: chosen || null,
    proxiedUrl: chosen ? `/proxy?url=${encodeURIComponent(chosen)}&w=${width}` : null,
    isWeak: isWeakVisual(chosen),
  };
}
