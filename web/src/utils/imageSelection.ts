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
  'ogimage',
  'opengraph',
  'share-image',
  'site-share',
];

export function isWeakVisual(url?: string | null) {
  const value = String(url || '').toLowerCase().trim();
  if (!value) return true;
  return WEAK_VISUAL_TOKENS.some((token) => value.includes(token));
}

export function chooseClusterImage(cluster: ClusterLike) {
  const candidates = [
    cluster?.representative_image,
    cluster?.articles?.[0]?.image_url,
    ...((cluster?.articles || []).map((article) => article?.image_url)),
  ].filter(Boolean) as string[];

  const preferred = candidates.find((candidate) => !isWeakVisual(candidate));
  const chosen = preferred || candidates[0] || '';

  return {
    rawUrl: chosen || null,
    proxiedUrl: chosen ? `/proxy?url=${encodeURIComponent(chosen)}` : null,
    isWeak: isWeakVisual(chosen),
  };
}
