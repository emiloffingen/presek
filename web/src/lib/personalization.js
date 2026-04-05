const PROFILE_KEY = 'presek_reader_profile_v1';
const MAX_RECENT_CLUSTERS = 24;
const MAX_FOLLOWED = 12;

function normalizeValue(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function normalizeList(values) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map((item) => normalizeValue(item))
        .filter(Boolean)
    )
  );
}

function safeParse(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function createEmptyProfile() {
  return {
    recentClusters: [],
    followedTopics: [],
    followedSources: [],
  };
}

export function loadReaderProfile(storage = globalThis?.localStorage) {
  if (!storage) return createEmptyProfile();
  const parsed = safeParse(storage.getItem(PROFILE_KEY));
  return {
    recentClusters: Array.isArray(parsed?.recentClusters) ? parsed.recentClusters : [],
    followedTopics: normalizeList(parsed?.followedTopics),
    followedSources: normalizeList(parsed?.followedSources),
  };
}

export function saveReaderProfile(profile, storage = globalThis?.localStorage) {
  if (!storage) return profile;
  const normalized = {
    recentClusters: Array.isArray(profile?.recentClusters) ? profile.recentClusters.slice(0, MAX_RECENT_CLUSTERS) : [],
    followedTopics: normalizeList(profile?.followedTopics).slice(0, MAX_FOLLOWED),
    followedSources: normalizeList(profile?.followedSources).slice(0, MAX_FOLLOWED),
  };
  storage.setItem(PROFILE_KEY, JSON.stringify(normalized));
  return normalized;
}

export function toggleFollowedValue(kind, value, storage = globalThis?.localStorage) {
  const cleanValue = normalizeValue(value);
  if (!cleanValue) return { profile: loadReaderProfile(storage), isFollowing: false };

  const profile = loadReaderProfile(storage);
  const field = kind === 'source' ? 'followedSources' : 'followedTopics';
  const existing = new Set(profile[field] || []);
  let isFollowing;

  if (existing.has(cleanValue)) {
    existing.delete(cleanValue);
    isFollowing = false;
  } else {
    existing.add(cleanValue);
    isFollowing = true;
  }

  profile[field] = Array.from(existing).slice(0, MAX_FOLLOWED);
  const saved = saveReaderProfile(profile, storage);
  return { profile: saved, isFollowing };
}

export function isFollowingValue(kind, value, storage = globalThis?.localStorage) {
  const cleanValue = normalizeValue(value);
  if (!cleanValue) return false;
  const profile = loadReaderProfile(storage);
  const field = kind === 'source' ? 'followedSources' : 'followedTopics';
  return (profile[field] || []).includes(cleanValue);
}

export function recordClusterView(record, storage = globalThis?.localStorage) {
  const profile = loadReaderProfile(storage);
  const normalized = {
    cluster_id: normalizeValue(record?.cluster_id),
    title: normalizeValue(record?.title),
    category: normalizeValue(record?.category),
    topic: normalizeValue(record?.topic),
    primarySource: normalizeValue(record?.primarySource),
    sources: normalizeList(record?.sources).slice(0, 8),
    tags: normalizeList(record?.tags).slice(0, 10),
    viewedAt: record?.viewedAt || new Date().toISOString(),
  };

  if (!normalized.cluster_id) return saveReaderProfile(profile, storage);

  const nextRecent = [
    normalized,
    ...(profile.recentClusters || []).filter((item) => item?.cluster_id !== normalized.cluster_id),
  ].slice(0, MAX_RECENT_CLUSTERS);

  profile.recentClusters = nextRecent;
  return saveReaderProfile(profile, storage);
}

function topCounts(values) {
  const counts = new Map();
  for (const value of values) {
    const clean = normalizeValue(value);
    if (!clean) continue;
    counts.set(clean, (counts.get(clean) || 0) + 1);
  }
  return counts;
}

export function buildReaderSignals(profile) {
  const recent = Array.isArray(profile?.recentClusters) ? profile.recentClusters : [];
  return {
    topicCounts: topCounts(recent.flatMap((item) => [item?.topic, item?.category])),
    sourceCounts: topCounts(recent.flatMap((item) => item?.sources?.length ? item.sources : [item?.primarySource])),
    tagCounts: topCounts(recent.flatMap((item) => item?.tags || [])),
  };
}

export function hasPersonalizationSignal(profile) {
  return Boolean(
    (profile?.recentClusters || []).length ||
      (profile?.followedTopics || []).length ||
      (profile?.followedSources || []).length
  );
}

function topReason(reasons) {
  return reasons.sort((left, right) => right.weight - left.weight)[0]?.label || '';
}

export function scoreClusterForReader(cluster, profile) {
  if (!cluster?.cluster_id || !Array.isArray(cluster?.articles) || cluster.articles.length === 0) {
    return null;
  }

  const main = cluster.articles[0] || {};
  const sources = normalizeList(cluster.articles.map((article) => article?.source));
  const clusterTags = normalizeList(cluster.tags || []);
  const clusterTopics = normalizeList([
    ...(cluster.topics || []),
    main.topic,
    main.category,
  ]);

  const signals = buildReaderSignals(profile);
  const followedTopics = new Set(normalizeList(profile?.followedTopics));
  const followedSources = new Set(normalizeList(profile?.followedSources));
  const seenClusterIds = new Set((profile?.recentClusters || []).map((item) => item?.cluster_id).filter(Boolean));

  let score = 0;
  const reasons = [];

  for (const topic of clusterTopics) {
    if (followedTopics.has(topic)) {
      score += 3;
      reasons.push({ weight: 3, label: `Следена тема: ${topic}` });
    }
    if (signals.topicCounts.has(topic)) {
      const weight = Math.min(2.2, 0.7 + signals.topicCounts.get(topic) * 0.55);
      score += weight;
      reasons.push({ weight, label: `Често читате ${topic}` });
    }
  }

  for (const source of sources) {
    if (followedSources.has(source)) {
      score += 2.6;
      reasons.push({ weight: 2.6, label: `Следен извор: ${source}` });
    }
    if (signals.sourceCounts.has(source)) {
      const weight = Math.min(1.8, 0.45 + signals.sourceCounts.get(source) * 0.35);
      score += weight;
      reasons.push({ weight, label: `${source} често се појавува во вашето читање` });
    }
  }

  for (const tag of clusterTags) {
    if (signals.tagCounts.has(tag)) {
      const weight = Math.min(1.9, 0.4 + signals.tagCounts.get(tag) * 0.4);
      score += weight;
      reasons.push({ weight, label: `Поврзано со ${tag}` });
    }
  }

  if (cluster.is_breaking) {
    score += 0.65;
  }
  score += Math.min(0.9, ((cluster.articles || []).length - 1) * 0.12);

  return {
    cluster,
    score,
    seen: seenClusterIds.has(cluster.cluster_id),
    reason: topReason(reasons),
  };
}

export function buildPersonalizedClusters(clusters, profile, limit = 4) {
  const scored = (Array.isArray(clusters) ? clusters : [])
    .map((cluster) => scoreClusterForReader(cluster, profile))
    .filter(Boolean)
    .filter((item) => item.score > 0.75)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      return (right.cluster?.homepage_score || 0) - (left.cluster?.homepage_score || 0);
    });

  const unseen = scored.filter((item) => !item.seen);
  return (unseen.length > 0 ? unseen : scored).slice(0, limit);
}

