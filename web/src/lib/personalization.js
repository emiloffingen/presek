const PROFILE_KEY = 'presek_reader_profile_v1';
const MAX_RECENT_CLUSTERS = 24;
const MAX_FOLLOWED = 12;
const DELIVERY_KEY = 'presek_delivery_prefs_v1';
const SYNC_TOKEN_KEY = 'presek_sync_token_v1';
const ONBOARDING_KEY = 'presek_onboarding_v1';
const SUGGESTION_ANALYTICS_KEY = 'presek_suggestion_analytics_v1';
const CLIENT_ID_KEY = 'presek_client_id_v1';
const MAX_SUGGESTION_IMPRESSION_KEYS = 240;
export const PROFILE_UPDATED_EVENT = 'presek:reader-profile-updated';
export const SYNC_TOKEN_UPDATED_EVENT = 'presek:sync-token-updated';
export const DELIVERY_PREFS_UPDATED_EVENT = 'presek:delivery-prefs-updated';
export const ONBOARDING_STATE_UPDATED_EVENT = 'presek:onboarding-updated';

const memoryStorage = {};
const dummyStorage = {
  getItem: (key) => memoryStorage[key] || null,
  setItem: (key, val) => { memoryStorage[key] = String(val); },
  removeItem: (key) => { delete memoryStorage[key]; },
  clear: () => { for (const k in memoryStorage) delete memoryStorage[k]; },
  key: (i) => Object.keys(memoryStorage)[i] || null,
  length: 0
};

function getSafeLocalStorage() {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.getItem('__test_access__');
      return window.localStorage;
    }
  } catch (e) {}
  return dummyStorage;
}

const safeStorage = getSafeLocalStorage();

const FOLLOW_RECOMMENDATION_MIN_SIGNAL = 1.25;
const HOME_RAIL_TOPIC_MIN_SIGNAL = 1.8;
const HOME_RAIL_SOURCE_MIN_SIGNAL = 3;
const FOR_YOU_TOPIC_MIN_SIGNAL = 1.8;
const FOR_YOU_SOURCE_MIN_SIGNAL = 1.25;
const SECONDARY_SOURCE_MIN_SIGNAL = 1.25;
const SURFACE_TOPIC_FALLBACK_MIN_SIGNAL = 0.65;

const SUGGESTION_SURFACE_LABELS = {
  sr: {
    onboarding: 'Početni vodič',
    home_rail: 'Početna desna kolona',
    cluster: 'stranica klastera',
    topic: 'stranica teme',
    for_you: 'Za Vas',
    settings: 'Podešavanja',
  },
  mk: {
    onboarding: 'Почетен водич',
    home_rail: 'Почетна десна колона',
    cluster: 'страница на кластер',
    topic: 'страница на тема',
    for_you: 'За Вас',
    settings: 'Подесувања',
  }
};

const SUGGESTION_KIND_LABELS = {
  sr: {
    topic: 'Teme',
    source: 'izvori',
  },
  mk: {
    topic: 'Теми',
    source: 'извори',
  }
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

function createKindSummary(kind, bucket, lang = 'mk') {
  const impressions = bucket?.impressions || 0;
  const follows = bucket?.follows || 0;
  const dismissals = bucket?.dismissals || 0;
  const labels = SUGGESTION_KIND_LABELS[lang] || SUGGESTION_KIND_LABELS.sr;
  return {
    kind,
    label: labels[kind] || kind,
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

export function loadSuggestionAnalytics(storage = safeStorage) {
  if (!storage) return createDefaultSuggestionAnalytics();
  const parsed = safeParse(storage.getItem(SUGGESTION_ANALYTICS_KEY));
  const next = createDefaultSuggestionAnalytics();
  next.surfaces = parsed?.surfaces && typeof parsed.surfaces === 'object' ? parsed.surfaces : {};
  next.impressionKeys = Array.isArray(parsed?.impressionKeys) ? parsed.impressionKeys : [];
  return next;
}

export function saveSuggestionAnalytics(analytics, storage = safeStorage) {
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

export function recordSuggestionImpressions(surface, suggestions, storage = safeStorage) {
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

export function recordSuggestionFollow(surface, kind, value, storage = safeStorage) {
  const cleanSurface = normalizeSurface(surface);
  const cleanValue = normalizeValue(value);
  if (!storage || !cleanSurface || !cleanValue) return { analytics: loadSuggestionAnalytics(storage), recorded: false };
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceBuckets = ensureSurfaceBuckets(analytics, cleanSurface);
  surfaceBuckets[normalizeSuggestionKind(kind)].follows += 1;
  return { analytics: saveSuggestionAnalytics(analytics, storage), recorded: true };
}

export function recordSuggestionDismiss(surface, storage = safeStorage) {
  const cleanSurface = normalizeSurface(surface);
  if (!storage || !cleanSurface) return { analytics: loadSuggestionAnalytics(storage), recorded: false };
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceBuckets = ensureSurfaceBuckets(analytics, cleanSurface);
  surfaceBuckets.topic.dismissals += 1;
  surfaceBuckets.source.dismissals += 1;
  return { analytics: saveSuggestionAnalytics(analytics, storage), recorded: true };
}

export function sendSuggestionEvents(events, storage = safeStorage) {
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
    headers: { 'Content-Type': 'application/json', ...buildCsrfHeaders() },
    body: JSON.stringify({
      token: loadSyncToken(storage),
      clientId: getOrCreateClientId(storage),
      events: cleanEvents,
    }),
    keepalive: true,
  }).catch(console.error);
}

export function getSuggestionConversionSummary(storage = safeStorage, lang = 'mk') {
  const analytics = loadSuggestionAnalytics(storage);
  const surfaceLabels = SUGGESTION_SURFACE_LABELS[lang] || SUGGESTION_SURFACE_LABELS.sr;
  const surfaces = Object.entries(analytics.surfaces || {})
    .map(([surface, buckets]) => {
      const topic = createKindSummary('topic', buckets?.topic, lang);
      const source = createKindSummary('source', buckets?.source, lang);
      const impressions = topic.impressions + source.impressions;
      const follows = topic.follows + source.follows;
      const dismissals = Math.max(topic.dismissals, source.dismissals);
      return {
        surface,
        label: surfaceLabels[surface] || surface,
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

export function loadSyncToken(storage = safeStorage) {
  if (!storage) return '';
  return normalizeValue(storage.getItem(SYNC_TOKEN_KEY));
}

export function getOrCreateClientId(storage = safeStorage) {
  if (!storage) return '';
  const existing = normalizeValue(storage.getItem(CLIENT_ID_KEY));
  if (existing) return existing;
  const next = `reader_${Math.random().toString(36).slice(2, 12)}${Date.now().toString(36).slice(-6)}`;
  storage.setItem(CLIENT_ID_KEY, next);
  return next;
}

export function saveSyncToken(token, storage = safeStorage) {
  const clean = normalizeValue(token);
  if (!storage) return clean;
  if (!clean) {
    storage.removeItem(SYNC_TOKEN_KEY);
    globalThis?.dispatchEvent?.(new CustomEvent(SYNC_TOKEN_UPDATED_EVENT, { detail: '' }));
    return '';
  }
  storage.setItem(SYNC_TOKEN_KEY, clean);
  globalThis?.dispatchEvent?.(new CustomEvent(SYNC_TOKEN_UPDATED_EVENT, { detail: clean }));
  return clean;
}

export function buildSyncTokenHeaders(token) {
  const clean = normalizeValue(token);
  return {
    ...buildCsrfHeaders(),
    ...(clean ? { 'X-Sync-Token': clean } : {}),
  };
}

export async function buildSyncTokenHeadersAsync(token) {
  const clean = normalizeValue(token);
  return {
    ...(await buildCsrfHeadersAsync()),
    ...(clean ? { 'X-Sync-Token': clean } : {}),
  };
}

export function getCsrfToken() {
  if (typeof document === 'undefined') return '';
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith('csrf_token='));
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : '';
}

export function buildCsrfHeaders() {
  const token = getCsrfToken();
  return token ? { 'X-CSRF-Token': token } : {};
}

export async function getCsrfTokenAsync() {
  const existing = getCsrfToken();
  if (existing || typeof fetch !== 'function') return existing;

  try {
    const res = await fetch('/api/csrf-token', {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
    });
    if (!res.ok) return getCsrfToken();
    const payload = await res.json();
    return payload?.csrf_token || getCsrfToken();
  } catch {
    return getCsrfToken();
  }
}

/**
 * @returns {Promise<Record<string, string>>}
 */
export async function buildCsrfHeadersAsync() {
  const token = await getCsrfTokenAsync();
  return token ? { 'X-CSRF-Token': token } : {};
}

export function loadReaderProfile(storage = safeStorage) {
  if (!storage) return createEmptyProfile();
  const parsed = safeParse(storage.getItem(PROFILE_KEY));
  return {
    recentClusters: Array.isArray(parsed?.recentClusters) ? parsed.recentClusters : [],
    followedTopics: normalizeList(parsed?.followedTopics),
    followedSources: normalizeList(parsed?.followedSources),
  };
}

export function saveReaderProfile(profile, storage = safeStorage) {
  if (!storage) return profile;
  const normalized = {
    recentClusters: Array.isArray(profile?.recentClusters) ? profile.recentClusters.slice(0, MAX_RECENT_CLUSTERS) : [],
    followedTopics: normalizeList(profile?.followedTopics).slice(0, MAX_FOLLOWED),
    followedSources: normalizeList(profile?.followedSources).slice(0, MAX_FOLLOWED),
  };
  storage.setItem(PROFILE_KEY, JSON.stringify(normalized));
  globalThis?.dispatchEvent?.(new CustomEvent(PROFILE_UPDATED_EVENT, { detail: normalized }));
  return normalized;
}

export function subscribeToReaderProfile(listener) {
  if (!globalThis?.addEventListener || typeof listener !== 'function') {
    return () => {};
  }

  const onProfileUpdated = () => listener(loadReaderProfile());
  const onStorage = (event) => {
    if (event?.key && event.key !== PROFILE_KEY) return;
    listener(loadReaderProfile());
  };

  globalThis.addEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
  globalThis.addEventListener('storage', onStorage);

  return () => {
    globalThis.removeEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
    globalThis.removeEventListener('storage', onStorage);
  };
}

export function subscribeToSyncToken(listener) {
    if (!globalThis?.addEventListener || typeof listener !== 'function') return () => {};
    const onUpdated = () => listener(loadSyncToken());
    globalThis.addEventListener(SYNC_TOKEN_UPDATED_EVENT, onUpdated);
    return () => globalThis.removeEventListener(SYNC_TOKEN_UPDATED_EVENT, onUpdated);
}

export function subscribeToDeliveryPrefs(listener) {
    if (!globalThis?.addEventListener || typeof listener !== 'function') return () => {};
    const onUpdated = () => listener(loadDeliveryPreferences());
    globalThis.addEventListener(DELIVERY_PREFS_UPDATED_EVENT, onUpdated);
    return () => globalThis.removeEventListener(DELIVERY_PREFS_UPDATED_EVENT, onUpdated);
}

export function subscribeToOnboarding(listener) {
    if (!globalThis?.addEventListener || typeof listener !== 'function') return () => {};
    const onUpdated = () => listener(loadOnboardingState());
    globalThis.addEventListener(ONBOARDING_STATE_UPDATED_EVENT, onUpdated);
    return () => globalThis.removeEventListener(ONBOARDING_STATE_UPDATED_EVENT, onUpdated);
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
  const channel = normalizeValue(next.channel) === 'webpush' ? 'webpush' : 'ntfy';
  let target = normalizeValue(next.target);

  if (channel === 'ntfy') {
    target = target.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-._]+|[-._]+$/g, '').slice(0, 120);
  }

  return {
    channel,
    target,
    morningBriefing: next.morningBriefing !== false,
    weeklyDigest: Boolean(next.weeklyDigest),
    breakingTopics: Boolean(next.breakingTopics),
    breakingSources: Boolean(next.breakingSources),
    isActive: Boolean(next.isActive) && Boolean(target),
  };
}

export function loadDeliveryPreferences(storage = safeStorage) {
  if (!storage) return createDefaultDeliveryPreferences();
  const parsed = safeParse(storage.getItem(DELIVERY_KEY));
  return {
    morningBriefing: parsed?.morningBriefing !== false,
    breakingAlerts: parsed?.breakingAlerts !== false,
    browserPermission: normalizeValue(parsed?.browserPermission) || 'default',
  };
}

export function saveDeliveryPreferences(prefs, storage = safeStorage) {
  if (!storage) return prefs;
  const normalized = {
    morningBriefing: prefs?.morningBriefing !== false,
    breakingAlerts: prefs?.breakingAlerts !== false,
    browserPermission: normalizeValue(prefs?.browserPermission) || 'default',
  };
  storage.setItem(DELIVERY_KEY, JSON.stringify(normalized));
  globalThis?.dispatchEvent?.(new CustomEvent(DELIVERY_PREFS_UPDATED_EVENT, { detail: normalized }));
  return normalized;
}

export function toggleDeliveryPreference(field, storage = safeStorage) {
  const prefs = loadDeliveryPreferences(storage);
  if (field !== 'morningBriefing' && field !== 'breakingAlerts') {
    return prefs;
  }
  prefs[field] = !prefs[field];
  return saveDeliveryPreferences(prefs, storage);
}

export function setBrowserPermissionStatus(status, storage = safeStorage) {
  const prefs = loadDeliveryPreferences(storage);
  prefs.browserPermission = normalizeValue(status) || 'default';
  return saveDeliveryPreferences(prefs, storage);
}

export function toggleFollowedValue(kind, value, storage = safeStorage) {
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

export function isFollowingValue(kind, value, storage = safeStorage) {
  const cleanValue = normalizeValue(value);
  if (!cleanValue) return false;
  const profile = loadReaderProfile(storage);
  const field = kind === 'source' ? 'followedSources' : 'followedTopics';
  return (profile[field] || []).includes(cleanValue);
}

export function recordClusterView(record, storage = safeStorage) {
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

function parseViewedAt(value) {
  const stamp = String(value || '').trim();
  if (!stamp) return null;
  const time = Date.parse(stamp);
  return Number.isFinite(time) ? time : null;
}

function recencyWeight(viewedAt, now = Date.now()) {
  const parsed = parseViewedAt(viewedAt);
  if (!parsed) return 0.7;

  const ageMs = Math.max(0, now - parsed);
  const ageDays = ageMs / (1000 * 60 * 60 * 24);

  if (ageDays <= 2) return 1;
  if (ageDays <= 7) return 0.82;
  if (ageDays <= 14) return 0.58;
  if (ageDays <= 30) return 0.32;
  return 0.14;
}

function topWeightedCounts(items, selector, now = Date.now()) {
  const counts = new Map();

  for (const item of Array.isArray(items) ? items : []) {
    const weight = recencyWeight(item?.viewedAt, now);
    const values = Array.isArray(selector(item)) ? selector(item) : [];

    for (const value of values) {
      const clean = normalizeValue(value);
      if (!clean) continue;
      counts.set(clean, Number(((counts.get(clean) || 0) + weight).toFixed(3)));
    }
  }

  return counts;
}

export function buildReaderSignals(profile) {
  const recent = Array.isArray(profile?.recentClusters) ? profile.recentClusters : [];
  return {
    topicCounts: topWeightedCounts(recent, (item) => [item?.topic, item?.category]),
    sourceCounts: topWeightedCounts(recent, (item) => item?.sources?.length ? item.sources : [item?.primarySource]),
    tagCounts: topWeightedCounts(recent, (item) => item?.tags || []),
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

function normalizedLabelKey(value) {
  return normalizeValue(value).toLocaleLowerCase('mk');
}

function isWeakRecommendationValue(value) {
  const clean = normalizedLabelKey(value);
  if (!clean) return true;
  return [
    'vesti',
    'Srbija',
    'Svet',
    'Balkan',
    'Sport',
    'Kultura',
    'Tehnologija',
    'zivot',
  ].includes(clean);
}

function isStrongTopicSignal(value) {
  return !isWeakRecommendationValue(value);
}

function distinctByValue(items, limit) {
  const seen = new Set();
  const next = [];

  for (const item of Array.isArray(items) ? items : []) {
    const key = normalizedLabelKey(item?.value);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    next.push(item);
    if (next.length >= limit) break;
  }

  return next;
}

function buildTopicSignalFallbacks(topicCounts, followedTopics, existingTopics, limit, lang = 'mk') {
  const existing = new Set((existingTopics || []).map((item) => normalizedLabelKey(item?.value)));
  const isMK = lang === 'mk';
  return distinctByValue(
    Array.from(topicCounts.entries())
      .filter(([topic, count]) => (
        topic &&
        count >= SURFACE_TOPIC_FALLBACK_MIN_SIGNAL &&
        !followedTopics.has(topic) &&
        !isWeakRecommendationValue(topic) &&
        !existing.has(normalizedLabelKey(topic))
      ))
      .sort((left, right) => {
        if (right[1] !== left[1]) return right[1] - left[1];
        return left[0].localeCompare(right[0], 'mk');
      })
      .map(([topic, count]) => ({
        value: topic,
        count,
        reason: count >= FOLLOW_RECOMMENDATION_MIN_SIGNAL
          ? (isMK ? `оваа тема се повторува во вашето читање` : `ova tema se ponavlja u vašem čitanju`)
          : (isMK ? `се појавува како споредна тема во кластерите што ги читате` : `Pojavljuje se kao sporedna tema u klasterima koje čitate`),
      })),
    limit
  );
}

export function scoreClusterForReader(cluster, profile, lang = 'mk') {
  if (!cluster?.cluster_id || !Array.isArray(cluster?.articles) || cluster.articles.length === 0) {
    return null;
  }

  const isMK = lang === 'mk';
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
      score += 3.2;
      reasons.push({ weight: 3.2, label: isMK ? `Следена тема: ${topic}` : `Praćena tema: ${topic}` });
    }
    if (isStrongTopicSignal(topic) && signals.topicCounts.has(topic)) {
      const weight = Math.min(2.7, 0.55 + signals.topicCounts.get(topic) * 0.5);
      score += weight;
      reasons.push({ weight, label: isMK ? `Често читате ${topic}` : `Često čitate ${topic}` });
    }
  }

  for (const source of sources) {
    if (followedSources.has(source)) {
      score += 2.9;
      reasons.push({ weight: 2.9, label: isMK ? `Следен извор: ${source}` : `Praćeni izvor: ${source}` });
    }
    if (signals.sourceCounts.has(source)) {
      const weight = Math.min(1.65, 0.3 + signals.sourceCounts.get(source) * 0.28);
      score += weight;
      reasons.push({ weight, label: isMK ? `${source} често се појавува во вашето читање` : `${source} često se pojavljuje u vašem čitanju` });
    }
  }

  for (const tag of clusterTags) {
    if (signals.tagCounts.has(tag)) {
      const weight = Math.min(1.9, 0.4 + signals.tagCounts.get(tag) * 0.4);
      score += weight;
      reasons.push({ weight, label: isMK ? `Поврзано со ${tag}` : `Povezano sa ${tag}` });
    }
  }

  if (cluster.is_breaking) {
    score += 0.65;
  }
  score += Math.min(0.9, ((cluster.articles || []).length - 1) * 0.12);
  if (seenClusterIds.has(cluster.cluster_id)) {
    score -= 1.2;
  }

  reasons.sort((left, right) => right.weight - left.weight);

  return {
    cluster,
    score,
    seen: seenClusterIds.has(cluster.cluster_id),
    reason: topReason(reasons),
    matchReasons: reasons.slice(0, 3).map((item) => item.label),
    matchedTopics: clusterTopics.filter((topic) => followedTopics.has(topic)),
    matchedSources: sources.filter((source) => followedSources.has(source)),
  };
}

export function buildPersonalizedClusters(clusters, profile, limit = 4, excludeClusterIds = [], lang = 'mk') {
  const excludeSet = new Set(excludeClusterIds);
  const scored = (Array.isArray(clusters) ? clusters : [])
    .map((cluster) => scoreClusterForReader(cluster, profile, lang))
    .filter(Boolean)
    .filter((item) => item.score > 1.45 && !excludeSet.has(item.cluster?.cluster_id))
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      return (right.cluster?.homepage_score || 0) - (left.cluster?.homepage_score || 0);
    });

  const unseen = scored.filter((item) => !item.seen);
  return (unseen.length > 0 ? unseen : scored).slice(0, limit);
}

export function buildDeliveryDigest(content, profile, prefs, lang = 'mk') {
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
  const isMK = lang === 'mk';

  if (prefs?.morningBriefing !== false) {
    introBits.push(isMK ? 'Вашиот дневен брифинг е подготвен.' : 'Vaš dnevni brifing je spreman.');
  }
  if (followedTopics.length > 0) {
    introBits.push(isMK ? `Следени теми: ${followedTopics.join(', ')}.` : `Praćene teme: ${followedTopics.join(', ')}.`);
  }
  if (followedSources.length > 0) {
    introBits.push(isMK ? `Следени извори: ${followedSources.join(', ')}.` : `Praćeni izvori: ${followedSources.join(', ')}.`);
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

export function loadOnboardingState(storage = safeStorage) {
  if (!storage) return createDefaultOnboardingState();
  const parsed = safeParse(storage.getItem(ONBOARDING_KEY));
  return {
    dismissed: Boolean(parsed?.dismissed),
    completedAt: normalizeValue(parsed?.completedAt),
  };
}

export function saveOnboardingState(state, storage = safeStorage) {
  const normalized = {
    dismissed: Boolean(state?.dismissed),
    completedAt: normalizeValue(state?.completedAt),
  };
  if (storage) {
    storage.setItem(ONBOARDING_KEY, JSON.stringify(normalized));
    globalThis?.dispatchEvent?.(new CustomEvent(ONBOARDING_STATE_UPDATED_EVENT, { detail: normalized }));
  }
  return normalized;
}

export function dismissOnboarding(storage = safeStorage) {
  return saveOnboardingState({ ...loadOnboardingState(storage), dismissed: true }, storage);
}

export function completeOnboarding(storage = safeStorage) {
  return saveOnboardingState(
    {
      dismissed: true,
      completedAt: new Date().toISOString(),
    },
    storage
  );
}

export function getOnboardingProgress(storage = safeStorage, lang = 'mk') {
  const profile = loadReaderProfile(storage);
  const delivery = loadDeliveryPreferences(storage);
  const syncToken = loadSyncToken(storage);
  const onboarding = loadOnboardingState(storage);
  const isMK = lang === 'mk';

  const steps = [
    {
      id: 'read',
      label: isMK ? 'Отворете неколку кластери' : 'Otvorite nekoliko klastera',
      done: (profile.recentClusters || []).length >= 2,
    },
    {
      id: 'topic',
      label: isMK ? 'Следете 2 теми' : 'Sledete 2 temi',
      done: (profile.followedTopics || []).length >= 2,
    },
    {
      id: 'source',
      label: isMK ? 'Следете 1 извор' : 'Sledete 1 izvor',
      done: (profile.followedSources || []).length >= 1,
    },
    {
      id: 'delivery',
      label: isMK ? 'Вклучете известувања или достава' : 'Vključite obaveštenja ili dostavu',
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

export function buildFollowRecommendations(profile, limit = 4, lang = 'mk') {
  const normalizedProfile = profile || createEmptyProfile();
  const signals = buildReaderSignals(normalizedProfile);
  const topicSignals = signals.topicCounts;
  const sourceSignals = signals.sourceCounts;
  const followedTopics = new Set(normalizeList(normalizedProfile.followedTopics));
  const followedSources = new Set(normalizeList(normalizedProfile.followedSources));
  const isMK = lang === 'mk';

  const topicRecommendations = distinctByValue(
    Array.from(topicSignals.entries())
    .filter(([topic, count]) => (
      topic &&
      count >= FOLLOW_RECOMMENDATION_MIN_SIGNAL &&
      !followedTopics.has(topic) &&
      !isWeakRecommendationValue(topic)
    ))
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0], 'mk');
    })
    .map(([topic, count]) => {
      let reason = '';
      if (isMK) {
        reason = count >= 3 ? `Често читате теми поврзани со ${topic}` : `Оваа тема се повторува во вашето читање`;
      } else {
        reason = count >= 3 ? `Često čitate teme povezane sa ${topic}` : `Ova tema se ponavlja u vašem čitanju`;
      }
      return { value: topic, count, reason };
    }),
    limit
  );

  const sourceRecommendations = distinctByValue(
    Array.from(sourceSignals.entries())
    .filter(([source, count]) => source && count >= FOLLOW_RECOMMENDATION_MIN_SIGNAL && !followedSources.has(source))
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0], 'mk');
    })
    .map(([source, count]) => {
      let reason = '';
      if (isMK) {
        reason = count >= 3 ? `${source} постојано се појавува во вашето читање` : `Овој извор се повторува низ кластерите што ги отворате`;
      } else {
        reason = count >= 3 ? `${source} se stalno pojavljuje u vašem čitanju` : `Ovaj izvor se ponavlja kroz klastere koje otvarate`;
      }
      return { value: source, count, reason };
    }),
    limit
  );

  return {
    topics: topicRecommendations,
    sources: sourceRecommendations,
  };
}

export function buildSurfaceFollowSuggestions(profile, surface, options = {}) {
  const cleanSurface = normalizeSurface(surface);
  const normalizedProfile = profile || createEmptyProfile();
  const lang = options.lang || 'sr';
  const topicLimit = Number.isFinite(options.topicLimit) ? Math.max(0, options.topicLimit) : 2;
  const sourceLimit = Number.isFinite(options.sourceLimit) ? Math.max(0, options.sourceLimit) : 1;
  const recommendations = buildFollowRecommendations(normalizedProfile, Math.max(4, topicLimit + sourceLimit + 2), lang);
  const signals = buildReaderSignals(normalizedProfile);
  const topicCounts = signals.topicCounts;
  const sourceCounts = signals.sourceCounts;
  const followedCount = (normalizedProfile.followedTopics || []).length + (normalizedProfile.followedSources || []).length;
  const hasSignals = hasPersonalizationSignal(normalizedProfile);

  let topics = [...recommendations.topics];
  let sources = [...recommendations.sources];

  if (cleanSurface === 'onboarding') {
    topics = topics.slice(0, topicLimit || 2);
    sources = followedCount > 0 ? sources.slice(0, Math.min(1, sourceLimit || 1)) : [];
  } else if (cleanSurface === 'home_rail') {
    topics = topics.filter((item) => (topicCounts.get(item.value) || 0) >= HOME_RAIL_TOPIC_MIN_SIGNAL).slice(0, topicLimit || 2);
    if (topics.length < topicLimit) {
      topics = distinctByValue([
        ...topics,
        ...buildTopicSignalFallbacks(topicCounts, new Set(normalizeList(normalizedProfile.followedTopics)), topics, topicLimit, lang),
      ], topicLimit);
    }
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= HOME_RAIL_SOURCE_MIN_SIGNAL).slice(0, hasSignals ? 0 : 1);
  } else if (cleanSurface === 'for_you') {
    topics = topics.filter((item) => (topicCounts.get(item.value) || 0) >= FOR_YOU_TOPIC_MIN_SIGNAL).slice(0, topicLimit || 2);
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= FOR_YOU_SOURCE_MIN_SIGNAL).slice(0, sourceLimit || 1);
    if (topics.length === 0 && sources.length === 0) {
      sources = recommendations.sources.filter((item) => (sourceCounts.get(item.value) || 0) >= SECONDARY_SOURCE_MIN_SIGNAL).slice(0, Math.min(1, sourceLimit || 1));
    }
  } else if (cleanSurface === 'settings') {
    topics = topics.slice(0, Math.max(2, topicLimit));
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= SECONDARY_SOURCE_MIN_SIGNAL).slice(0, Math.max(1, sourceLimit));
  } else if (cleanSurface === 'cluster' || cleanSurface === 'topic') {
    topics = topics.slice(0, Math.max(2, topicLimit));
    sources = sources.filter((item) => (sourceCounts.get(item.value) || 0) >= SECONDARY_SOURCE_MIN_SIGNAL).slice(0, Math.max(1, sourceLimit));
  } else {
    topics = topics.slice(0, topicLimit);
    sources = sources.slice(0, sourceLimit);
  }

  return { topics, sources };
}

export function exportSyncPayload(storage = safeStorage) {
  return {
    followedTopics: loadReaderProfile(storage).followedTopics,
    followedSources: loadReaderProfile(storage).followedSources,
    recentClusters: loadReaderProfile(storage).recentClusters,
    deliveryPreferences: loadDeliveryPreferences(storage),
  };
}

export function clearAllData(storage = safeStorage) {
  if (!storage) return;
  const keys = [
    PROFILE_KEY,
    DELIVERY_KEY,
    SYNC_TOKEN_KEY,
    ONBOARDING_KEY,
    SUGGESTION_ANALYTICS_KEY,
    CLIENT_ID_KEY,
  ];
  for (const key of keys) {
    storage.removeItem(key);
  }
}

export function mergeSyncPayload(remoteProfile, storage = safeStorage) {
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
