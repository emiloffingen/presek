const SOFT_EXCLUDE_TOPICS = new Set(['Живот', 'Забава', 'Здравје']);
const HARD_NEWS_TOPICS = new Set(['Политика', 'Економија', 'Криминал', 'Спорт', 'Технологија']);
const FEATURE_PATTERNS = [
  /издание на/i,
  /интервју со/i,
  /интервју\b/i,
  /проверете дали/i,
  /пред да /i,
  /постојано сте уморни/i,
  /овој минерал/i,
  /хороскоп/i,
  /рецепт/i,
  /фото\b/i,
  /видео\b/i,
  /галерија/i,
];

function parseTime(value) {
  const ts = Date.parse(String(value || ''));
  return Number.isFinite(ts) ? ts : 0;
}

function titleLooksLikeFeature(title) {
  const clean = String(title || '').trim();
  if (!clean) return true;
  if (clean.length > 180) return true;
  if (clean.includes('?')) return true;
  return FEATURE_PATTERNS.some((pattern) => pattern.test(clean));
}

function primaryArticle(cluster) {
  return cluster?.articles?.[0] || {};
}

export function isLiveNowCandidate(cluster) {
  const article = primaryArticle(cluster);
  const title = String(article.title || '').trim();
  const topic = String(article.topic || '').trim();
  const category = String(article.category || '').trim();

  if (!title) return false;

  if (cluster?.is_breaking) return true;

  if (titleLooksLikeFeature(title)) return false;
  if (SOFT_EXCLUDE_TOPICS.has(topic)) return false;

  if (HARD_NEWS_TOPICS.has(topic)) return true;
  if (category && !['Македонија', 'Балкан', 'Европа', 'Германија', 'Америка', 'Свет'].includes(category)) {
    return false;
  }

  return (cluster?.articles?.length || 0) >= 2;
}

export function rankLiveNowClusters(items, excludeClusterIds = []) {
  const exclude = new Set(excludeClusterIds);
  const sourceCount = {};

  return (Array.isArray(items) ? items : [])
    .filter((cluster) => cluster && !exclude.has(cluster.cluster_id))
    .filter(isLiveNowCandidate)
    .sort((left, right) => {
      const leftBreaking = left?.is_breaking ? 1 : 0;
      const rightBreaking = right?.is_breaking ? 1 : 0;
      if (rightBreaking !== leftBreaking) return rightBreaking - leftBreaking;

      const leftHard = HARD_NEWS_TOPICS.has(String(primaryArticle(left).topic || '').trim()) ? 1 : 0;
      const rightHard = HARD_NEWS_TOPICS.has(String(primaryArticle(right).topic || '').trim()) ? 1 : 0;
      if (rightHard !== leftHard) return rightHard - leftHard;

      return parseTime(primaryArticle(right).created_at) - parseTime(primaryArticle(left).created_at);
    })
    .filter((cluster) => {
      const src = String(primaryArticle(cluster).source || 'unknown');
      sourceCount[src] = (sourceCount[src] || 0) + 1;
      return sourceCount[src] <= 1;
    });
}

export function isLatestWireArticleCandidate(article) {
  const title = String(article?.title || '').trim();
  const topic = String(article?.topic || '').trim();
  const category = String(article?.category || '').trim();

  if (!title || titleLooksLikeFeature(title)) return false;
  if (SOFT_EXCLUDE_TOPICS.has(topic)) return false;
  if (HARD_NEWS_TOPICS.has(topic)) return true;
  return ['Македонија', 'Балкан', 'Европа', 'Германија', 'Америка', 'Свет'].includes(category);
}

export function rankLatestWireArticles(items, limit = 15) {
  const seenTitles = new Set();
  const sourceCount = {};

  return (Array.isArray(items) ? items : [])
    .filter(isLatestWireArticleCandidate)
    .filter((article) => {
      const normalizedTitle = String(article?.title || '').trim().toLowerCase();
      if (!normalizedTitle || seenTitles.has(normalizedTitle)) return false;
      seenTitles.add(normalizedTitle);
      return true;
    })
    .sort((left, right) => {
      const leftHard = HARD_NEWS_TOPICS.has(String(left?.topic || '').trim()) ? 1 : 0;
      const rightHard = HARD_NEWS_TOPICS.has(String(right?.topic || '').trim()) ? 1 : 0;
      if (rightHard !== leftHard) return rightHard - leftHard;
      return parseTime(right?.created_at) - parseTime(left?.created_at);
    })
    .filter((article) => {
      const src = String(article?.source || 'unknown');
      sourceCount[src] = (sourceCount[src] || 0) + 1;
      return sourceCount[src] <= 2;
    })
    .slice(0, limit);
}
