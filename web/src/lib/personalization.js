const PROFILE_KEY = 'presek_reader_profile_v1';
const MAX_RECENT_CLUSTERS = 24;
const MAX_FOLLOWED = 12;
const DELIVERY_KEY = 'presek_delivery_prefs_v1';
const SYNC_TOKEN_KEY = 'presek_sync_token_v1';
const ONBOARDING_KEY = 'presek_onboarding_v1';
const SUGGESTION_ANALYTICS_KEY = 'presek_suggestion_analytics_v1';
const CLIENT_ID_KEY = 'presek_client_id_v1';
const MAX_SUGGESTION_IMPRESSION_KEYS = 240;

const SUGGESTION_SURFACE_LABELS = {
  onboarding: 'Почетен водич',
  home_rail: 'Почетна десна колона',
  cluster: 'Кластер страница',
  topic: 'Тема страница',
  for_you: 'За Вас',
  settings: 'Поставки',
};

const SUGGESTION_KIND_LABELS = {
  topic: 'Теми',
  source: 'Извори',
};

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

function todayStamp() {
  return new Date().toISOString().slice(0, 10);
}

function normalizeSurface(surface) {
  return normalizeValue(surface).toLowerCase().replace(/[^a-z0-9_:-]+/g, '_');
}

function createSuggestionBucket() {
  return {
    impressions: 0,
    follows: 0,
    dismissals: 0,
  };
}

function normalizeSuggestionKind(kind) {
  return kind === 'source' ? 'source' : 'topic';
}

function normalizeSuggestionEventType(eventType) {
  const clean = normalizeValue(eventType).toLowerCase();
  return ['impression', 'follow', 'dismiss'].includes(clean) ? clean : '';
}

function createKindSummary(kind, bucket) {
  const impressions = bucket?.impressions || 0;
  const follows = bucket?.follows || 0;
  const dismissals = bucket?.dismissals || 0;
  return {
    kind,
    label: SUGGESTION_KIND_LABELS[kind] || kind,
    impressions,
    follows,
    dismissals,
    conversion_rate: impressions > 0 ? Number(((follows / impressions) * 100).toFixed(1)) : 0,
  };
}

export function createDefaultSuggestionAnalytics() {
  return {
    surfaces: {},
    impressionKeys: [],
  };
}

export function loadSuggestionAnalytics(storage = globalThis?.localStorage) {
  if (!storage) return createDefaultSuggestionAnalytics();
  const parsed = safeParse(storage.getItem(SUGGESTION_ANALYTICS_KEY));
  const next = createDefaultSuggestionAnalytics();
  next.surfaces = parsed?.surfaces && typeof parsed.surfaces === 'object' ? parsed.surfaces : {};
  next.impressionKeys = Array.isArray(parsed?.impressionKeys) ? parsed.impressionKeys : [];
  return next;
}

export function saveSuggestionAnalytics(analytics, storage = globalThis?.localStorage) {
  const normalized = createDefaultSuggestionAnalytics();
  normalized.surfaces = analytics?.surfaces && typeof analytics.surfaces === 'object' ? analytics.surfaces : {};
  normalized.impressionKeys = Array.isArray(analytics?.impressionKeys)
    ? analytics.impressionKeys.slice(-MAX_SUGGESTION_IMPRESSION_KEYS)
    : [];
  if (storage) {
    storage.setItem(SUGGESTION_ANALYTICS_KEY, JSON.stringify(normalized));
  }
  return normalized;
}

function ensureSurfaceBuckets(analytics, surface) {
  if (!analytics.surfaces[surface]) {
    analytics.surfaces[surface] = {
      topic: createSuggestionBucket(),
      source: createSuggestionBucket(),
    };
  }
  for (const kind of ['topic', 'source']) {
    if (!analytics.surfaces[surface][kind]) {
      analytics.surfaces[surface][kind] = createSuggestionBucket();
    }
  }
  return analytics.surfaces[surface];
}

export function recordSuggestionImpressions(surface, suggestions, storage = globalThis?.localStorage) {
  const cleanSurface = normalizeSurface(surface);
  if (!storage || !cleanSurface) return { analytics: loadSuggestionAnalytics(storage), recorded: [] };
  const items = (Array.isArray(suggestions) ? suggestions : [])
    .map((item) => ({
      kind: normalizeSuggestionKind(item?.kind),
      value: normalizeValue(item?.value),
    }))
    .filter((item) => item.value);

  if (items.length === 0) {
    return { analytics: loadSuggestionAnalytics(storage), recorded: [] };
  }

  const stamp = todayStamp();
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceBuckets = ensureSurfaceBuckets(analytics, cleanSurface);
  const knownKeys = new Set(analytics.impressionKeys || []);
  const recorded = [];

  for (const item of items) {
    const dedupeKey = `${stamp}:${cleanSurface}:${item.kind}:${item.value}`;
    if (knownKeys.has(dedupeKey)) continue;
    knownKeys.add(dedupeKey);
    analytics.impressionKeys.push(dedupeKey);
    surfaceBuckets[item.kind].impressions += 1;
    recorded.push(item);
  }

  analytics.impressionKeys = analytics.impressionKeys.slice(-MAX_SUGGESTION_IMPRESSION_KEYS);
  return { analytics: saveSuggestionAnalytics(analytics, storage), recorded };
}

export function recordSuggestionFollow(surface, kind, value, storage = globalThis?.localStorage) {
  const cleanSurface = normalizeSurface(surface);
  const cleanValue = normalizeValue(value);
  if (!storage || !cleanSurface || !cleanValue) return { analytics: loadSuggestionAnalytics(storage), recorded: false };
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceBuckets = ensureSurfaceBuckets(analytics, cleanSurface);
  surfaceBuckets[normalizeSuggestionKind(kind)].follows += 1;
  return { analytics: saveSuggestionAnalytics(analytics, storage), recorded: true };
}

export function recordSuggestionDismiss(surface, storage = globalThis?.localStorage) {
  const cleanSurface = normalizeSurface(surface);
  if (!storage || !cleanSurface) return { analytics: loadSuggestionAnalytics(storage), recorded: false };
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceBuckets = ensureSurfaceBuckets(analytics, cleanSurface);
  surfaceBuckets.topic.dismissals += 1;
  surfaceBuckets.source.dismissals += 1;
  return { analytics: saveSuggestionAnalytics(analytics, storage), recorded: true };
}

export function sendSuggestionEvents(events, storage = globalThis?.localStorage) {
  const fetchImpl = globalThis?.fetch;
  if (!storage || typeof fetchImpl !== 'function') return;

  const cleanEvents = (Array.isArray(events) ? events : [])
    .map((item) => ({
      surface: normalizeSurface(item?.surface),
      eventType: normalizeSuggestionEventType(item?.eventType),
      suggestionKind: normalizeSuggestionKind(item?.suggestionKind),
      value: normalizeValue(item?.value).slice(0, 160),
    }))
    .filter((item) => item.surface && item.eventType)
    .map((item) => ({
      ...item,
      suggestionKind: item.eventType === 'dismiss' ? '' : item.suggestionKind,
    }));

  if (cleanEvents.length === 0) return;

  fetchImpl('/api/profile/suggestion-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      token: loadSyncToken(storage),
      clientId: getOrCreateClientId(storage),
      events: cleanEvents,
    }),
    keepalive: true,
  }).catch(() => {});
}

export function getSuggestionConversionSummary(storage = globalThis?.localStorage) {
  const analytics = loadSuggestionAnalytics(storage);
  const surfaces = Object.entries(analytics.surfaces || {})
    .map(([surface, buckets]) => {
      const topic = createKindSummary('topic', buckets?.topic);
      const source = createKindSummary('source', buckets?.source);
      const impressions = topic.impressions + source.impressions;
      const follows = topic.follows + source.follows;
      const dismissals = Math.max(topic.dismissals, source.dismissals);
      return {
        surface,
        label: SUGGESTION_SURFACE_LABELS[surface] || surface,
        impressions,
        follows,
        dismissals,
        conversion_rate: impressions > 0 ? Number(((follows / impressions) * 100).toFixed(1)) : 0,
        by_kind: [topic, source],
      };
    })
    .filter((item) => item.impressions > 0 || item.follows > 0 || item.dismissals > 0)
    .sort((left, right) => {
      if (right.follows !== left.follows) return right.follows - left.follows;
      if (right.impressions !== left.impressions) return right.impressions - left.impressions;
      return left.label.localeCompare(right.label, 'mk');
    });

  const totals = {
    impressions: 0,
    follows: 0,
    dismissals: 0,
    by_kind: {
      topic: createKindSummary('topic', createSuggestionBucket()),
      source: createKindSummary('source', createSuggestionBucket()),
    },
  };

  for (const surface of surfaces) {
    totals.impressions += surface.impressions;
    totals.follows += surface.follows;
    totals.dismissals += surface.dismissals;
    for (const item of surface.by_kind) {
      const bucket = totals.by_kind[item.kind];
      bucket.impressions += item.impressions;
      bucket.follows += item.follows;
      bucket.dismissals += item.dismissals;
    }
  }

  totals.by_kind.topic = createKindSummary('topic', totals.by_kind.topic);
  totals.by_kind.source = createKindSummary('source', totals.by_kind.source);
  totals.conversion_rate = totals.impressions > 0 ? Number(((totals.follows / totals.impressions) * 100).toFixed(1)) : 0;

  return { surfaces, totals };
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

export function getOrCreateClientId(storage = globalThis?.localStorage) {
  if (!storage) return '';
  const existing = normalizeValue(storage.getItem(CLIENT_ID_KEY));
  if (existing) return existing;
  const next = `reader_${Math.random().toString(36).slice(2, 12)}${Date.now().toString(36).slice(-6)}`;
  storage.setItem(CLIENT_ID_KEY, next);
  return next;
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
    weeklyDigest: false,
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
    weeklyDigest: Boolean(next.weeklyDigest),
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

export function createDefaultOnboardingState() {
  return {
    dismissed: false,
    completedAt: '',
  };
}

export function loadOnboardingState(storage = globalThis?.localStorage) {
  if (!storage) return createDefaultOnboardingState();
  const parsed = safeParse(storage.getItem(ONBOARDING_KEY));
  return {
    dismissed: Boolean(parsed?.dismissed),
    completedAt: normalizeValue(parsed?.completedAt),
  };
}

export function saveOnboardingState(state, storage = globalThis?.localStorage) {
  const normalized = {
    dismissed: Boolean(state?.dismissed),
    completedAt: normalizeValue(state?.completedAt),
  };
  if (storage) {
    storage.setItem(ONBOARDING_KEY, JSON.stringify(normalized));
  }
  return normalized;
}

export function dismissOnboarding(storage = globalThis?.localStorage) {
  return saveOnboardingState({ ...loadOnboardingState(storage), dismissed: true }, storage);
}

export function completeOnboarding(storage = globalThis?.localStorage) {
  return saveOnboardingState(
    {
      dismissed: true,
      completedAt: new Date().toISOString(),
    },
    storage
  );
}

export function getOnboardingProgress(storage = globalThis?.localStorage) {
  const profile = loadReaderProfile(storage);
  const delivery = loadDeliveryPreferences(storage);
  const syncToken = loadSyncToken(storage);
  const onboarding = loadOnboardingState(storage);

  const steps = [
    {
      id: 'read',
      label: 'Отворете неколку кластери',
      done: (profile.recentClusters || []).length >= 2,
    },
    {
      id: 'topic',
      label: 'Следете 2 теми',
      done: (profile.followedTopics || []).length >= 2,
    },
    {
      id: 'source',
      label: 'Следете 1 извор',
      done: (profile.followedSources || []).length >= 1,
    },
    {
      id: 'delivery',
      label: 'Вклучете известувања или достава',
      done: delivery.browserPermission === 'granted' || Boolean(syncToken),
    },
  ];

  const doneCount = steps.filter((step) => step.done).length;
  const completed = doneCount === steps.length;
  return {
    steps,
    doneCount,
    total: steps.length,
    completed,
    dismissed: onboarding.dismissed,
    completedAt: onboarding.completedAt,
    shouldShow: !completed && !onboarding.dismissed,
  };
}

export function buildFollowRecommendations(profile, limit = 4) {
  const normalizedProfile = profile || createEmptyProfile();
  const topicSignals = buildReaderSignals(normalizedProfile).topicCounts;
  const sourceSignals = buildReaderSignals(normalizedProfile).sourceCounts;
  const followedTopics = new Set(normalizeList(normalizedProfile.followedTopics));
  const followedSources = new Set(normalizeList(normalizedProfile.followedSources));

  const topicRecommendations = Array.from(topicSignals.entries())
    .filter(([topic]) => topic && !followedTopics.has(topic))
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0], 'mk');
    })
    .slice(0, limit)
    .map(([topic, count]) => ({
      value: topic,
      reason: count >= 2 ? `Често читате теми поврзани со ${topic}` : `Се појавува во вашето неодамнешно читање`,
    }));

  const sourceRecommendations = Array.from(sourceSignals.entries())
    .filter(([source]) => source && !followedSources.has(source))
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0], 'mk');
    })
    .slice(0, limit)
    .map(([source, count]) => ({
      value: source,
      reason: count >= 2 ? `${source} често се појавува во вашето читање` : `Овој извор веќе е дел од кластерите што ги отворате`,
    }));

  return {
    topics: topicRecommendations,
    sources: sourceRecommendations,
  };
}

export function buildSurfaceFollowSuggestions(profile, surface, options = {}) {
  const cleanSurface = normalizeSurface(surface);
  const normalizedProfile = profile || createEmptyProfile();
  const topicLimit = Number.isFinite(options.topicLimit) ? Math.max(0, options.topicLimit) : 2;
  const sourceLimit = Number.isFinite(options.sourceLimit) ? Math.max(0, options.sourceLimit) : 1;
  const recommendations = buildFollowRecommendations(normalizedProfile, Math.max(4, topicLimit + sourceLimit + 2));
  const topicCounts = buildReaderSignals(normalizedProfile).topicCounts;
  const sourceCounts = buildReaderSignals(normalizedProfile).sourceCounts;
  const followedCount = (normalizedProfile.followedTopics || []).length + (normalizedProfile.followedSources || []).length;
  const hasSignals = hasPersonalizationSignal(normalizedProfile);

  let topics = [...recommendations.topics];
  let sources = [...recommendations.sources];

  if (cleanSurface === 'onboarding') {
    topics = topics.slice(0, topicLimit || 2);
    sources = followedCount > 0 ? sources.slice(0, Math.min(1, sourceLimit || 1)) : [];
  } else if (cleanSurface === 'home_rail') {
    topics = topics.slice(0, topicLimit || 2);
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= 2).slice(0, hasSignals ? 0 : 1);
  } else if (cleanSurface === 'for_you') {
    topics = topics.filter((item) => (topicCounts.get(item.value) || 0) >= 2).slice(0, topicLimit || 2);
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= 2).slice(0, sourceLimit || 1);
  } else if (cleanSurface === 'settings') {
    topics = topics.slice(0, Math.max(2, topicLimit));
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= 2).slice(0, Math.max(1, sourceLimit));
  } else if (cleanSurface === 'cluster' || cleanSurface === 'topic') {
    topics = topics.slice(0, Math.max(2, topicLimit));
    sources = sources.slice(0, Math.max(1, sourceLimit));
  } else {
    topics = topics.slice(0, topicLimit);
    sources = sources.slice(0, sourceLimit);
  }

  return { topics, sources };
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
