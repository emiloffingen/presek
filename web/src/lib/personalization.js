const PROFILE_KEY = 'presek_reader_profile_v1';
const MAX_RECENT_CLUSTERS = 24;
const MAX_FOLLOWED = 12;
const DELIVERY_KEY = 'presek_delivery_prefs_v1';
const SYNC_TOKEN_KEY = 'presek_sync_token_v1';

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

export function loadSyncToken(storage = globalThis?.localStorage) {
  if (!storage) return '';
  return normalizeValue(storage.getItem(SYNC_TOKEN_KEY));
}

export function saveSyncToken(token, storage = globalThis?.localStorage) {
  const clean = normalizeValue(token);
  if (!storage) return clean;
  if (!clean) {
    storage.removeItem(SYNC_TOKEN_KEY);
    return '';
  }
  storage.setItem(SYNC_TOKEN_KEY, clean);
  return clean;
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

export function createDefaultDeliveryPreferences() {
  return {
    morningBriefing: true,
    breakingAlerts: true,
    browserPermission: 'default',
  };
}

export function createDefaultServerDeliverySettings() {
  return {
    channel: 'ntfy',
    target: '',
    morningBriefing: true,
    breakingTopics: false,
    breakingSources: false,
    isActive: false,
  };
}

export function normalizeServerDeliverySettings(settings) {
  const next = settings || {};
  const target = normalizeValue(next.target).replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-._]+|[-._]+$/g, '').slice(0, 120);
  return {
    channel: 'ntfy',
    target,
    morningBriefing: next.morningBriefing !== false,
    breakingTopics: Boolean(next.breakingTopics),
    breakingSources: Boolean(next.breakingSources),
    isActive: Boolean(next.isActive) && Boolean(target),
  };
}

export function loadDeliveryPreferences(storage = globalThis?.localStorage) {
  if (!storage) return createDefaultDeliveryPreferences();
  const parsed = safeParse(storage.getItem(DELIVERY_KEY));
  return {
    morningBriefing: parsed?.morningBriefing !== false,
    breakingAlerts: parsed?.breakingAlerts !== false,
    browserPermission: normalizeValue(parsed?.browserPermission) || 'default',
  };
}

export function saveDeliveryPreferences(prefs, storage = globalThis?.localStorage) {
  if (!storage) return prefs;
  const normalized = {
    morningBriefing: prefs?.morningBriefing !== false,
    breakingAlerts: prefs?.breakingAlerts !== false,
    browserPermission: normalizeValue(prefs?.browserPermission) || 'default',
  };
  storage.setItem(DELIVERY_KEY, JSON.stringify(normalized));
  return normalized;
}

export function toggleDeliveryPreference(field, storage = globalThis?.localStorage) {
  const prefs = loadDeliveryPreferences(storage);
  if (field !== 'morningBriefing' && field !== 'breakingAlerts') {
    return prefs;
  }
  prefs[field] = !prefs[field];
  return saveDeliveryPreferences(prefs, storage);
}

export function setBrowserPermissionStatus(status, storage = globalThis?.localStorage) {
  const prefs = loadDeliveryPreferences(storage);
  prefs.browserPermission = normalizeValue(status) || 'default';
  return saveDeliveryPreferences(prefs, storage);
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

export function buildDeliveryDigest(content, profile, prefs) {
  const lines = String(content || '')
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const headlineLines = lines
    .filter((line) => line.startsWith('## ') || line.startsWith('### '))
    .slice(0, 5)
    .map((line) => line.replace(/^#{2,3}\s+/, ''));

  const followedTopics = normalizeList(profile?.followedTopics).slice(0, 3);
  const followedSources = normalizeList(profile?.followedSources).slice(0, 3);
  const introBits = [];

  if (prefs?.morningBriefing !== false) {
    introBits.push('Вашиот дневен брифинг е подготвен.');
  }
  if (followedTopics.length > 0) {
    introBits.push(`Следени теми: ${followedTopics.join(', ')}.`);
  }
  if (followedSources.length > 0) {
    introBits.push(`Следени извори: ${followedSources.join(', ')}.`);
  }

  return [
    ...introBits,
    ...headlineLines.map((line) => `• ${line}`),
  ].join('\n').trim();
}

export function exportSyncPayload(storage = globalThis?.localStorage) {
  return {
    followedTopics: loadReaderProfile(storage).followedTopics,
    followedSources: loadReaderProfile(storage).followedSources,
    recentClusters: loadReaderProfile(storage).recentClusters,
    deliveryPreferences: loadDeliveryPreferences(storage),
  };
}

export function mergeSyncPayload(remoteProfile, storage = globalThis?.localStorage) {
  const localProfile = loadReaderProfile(storage);
  const localPrefs = loadDeliveryPreferences(storage);
  const incomingProfile = remoteProfile || {};

  const mergedRecent = [];
  const seen = new Set();
  const combinedRecent = [
    ...(incomingProfile.recentClusters || []),
    ...(localProfile.recentClusters || []),
  ].sort((left, right) => String(right?.viewedAt || '').localeCompare(String(left?.viewedAt || '')));

  for (const item of combinedRecent) {
    const clusterId = normalizeValue(item?.cluster_id);
    if (!clusterId || seen.has(clusterId)) continue;
    seen.add(clusterId);
    mergedRecent.push({
      cluster_id: clusterId,
      title: normalizeValue(item?.title),
      category: normalizeValue(item?.category),
      topic: normalizeValue(item?.topic),
      primarySource: normalizeValue(item?.primarySource),
      sources: normalizeList(item?.sources || []).slice(0, 8),
      tags: normalizeList(item?.tags || []).slice(0, 10),
      viewedAt: normalizeValue(item?.viewedAt),
    });
    if (mergedRecent.length >= MAX_RECENT_CLUSTERS) break;
  }

  const mergedProfile = saveReaderProfile(
    {
      recentClusters: mergedRecent,
      followedTopics: normalizeList([...(localProfile.followedTopics || []), ...(incomingProfile.followedTopics || [])]),
      followedSources: normalizeList([...(localProfile.followedSources || []), ...(incomingProfile.followedSources || [])]),
    },
    storage
  );

  const mergedPrefs = saveDeliveryPreferences(
    {
      ...incomingProfile.deliveryPreferences,
      ...localPrefs,
    },
    storage
  );

  return { profile: mergedProfile, prefs: mergedPrefs };
}
