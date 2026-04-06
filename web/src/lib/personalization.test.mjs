import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildFollowRecommendations,
  buildDeliveryDigest,
  buildPersonalizedClusters,
  createDefaultOnboardingState,
  createDefaultSuggestionAnalytics,
  createEmptyProfile,
  dismissOnboarding,
  exportSyncPayload,
  getSuggestionConversionSummary,
  getOnboardingProgress,
  hasPersonalizationSignal,
  loadDeliveryPreferences,
  loadSuggestionAnalytics,
  loadSyncToken,
  mergeSyncPayload,
  recordSuggestionDismiss,
  recordSuggestionFollow,
  recordSuggestionImpressions,
  recordClusterView,
  saveDeliveryPreferences,
  saveSyncToken,
  toggleDeliveryPreference,
  toggleFollowedValue,
} from './personalization.js';

function makeStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, value);
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

function cluster(overrides = {}) {
  return {
    cluster_id: 'c1',
    homepage_score: 10,
    articles: [
      {
        title: 'Story',
        source: 'Telma',
        category: 'Политика',
        topic: 'Политика',
        description: 'desc',
      },
    ],
    tags: ['Собрание'],
    topics: ['Политика'],
    ...overrides,
  };
}

test('toggleFollowedValue stores followed topics', () => {
  const storage = makeStorage();
  const first = toggleFollowedValue('topic', 'Политика', storage);
  assert.equal(first.isFollowing, true);
  assert.deepEqual(first.profile.followedTopics, ['Политика']);

  const second = toggleFollowedValue('topic', 'Политика', storage);
  assert.equal(second.isFollowing, false);
  assert.deepEqual(second.profile.followedTopics, []);
});

test('recordClusterView keeps recent cluster data', () => {
  const storage = makeStorage();
  const profile = recordClusterView(
    {
      cluster_id: 'abc',
      title: 'Cluster',
      category: 'Политика',
      topic: 'Политика',
      primarySource: 'Telma',
      sources: ['Telma', '24 Вести'],
      tags: ['Собрание'],
    },
    storage
  );

  assert.equal(profile.recentClusters.length, 1);
  assert.equal(profile.recentClusters[0].cluster_id, 'abc');
  assert.deepEqual(profile.recentClusters[0].sources, ['Telma', '24 Вести']);
});

test('buildPersonalizedClusters prefers followed topics and unseen items', () => {
  const profile = createEmptyProfile();
  profile.followedTopics = ['Политика'];
  profile.recentClusters = [
    {
      cluster_id: 'seen-cluster',
      topic: 'Политика',
      category: 'Политика',
      primarySource: 'Telma',
      sources: ['Telma'],
      tags: ['Собрание'],
    },
  ];

  const items = buildPersonalizedClusters(
    [
      cluster({ cluster_id: 'seen-cluster' }),
      cluster({ cluster_id: 'fresh-cluster', articles: [{ title: 'Fresh', source: 'Alsat', category: 'Политика', topic: 'Политика', description: 'desc' }] }),
      cluster({ cluster_id: 'sports-cluster', articles: [{ title: 'Sports', source: 'MRT', category: 'Спорт', topic: 'Спорт', description: 'desc' }], topics: ['Спорт'], tags: ['Фудбал'] }),
    ],
    profile,
    2
  );

  assert.equal(items[0].cluster.cluster_id, 'fresh-cluster');
  assert.equal(items[0].reason, 'Следена тема: Политика');
});

test('hasPersonalizationSignal reflects reader activity or follows', () => {
  assert.equal(hasPersonalizationSignal(createEmptyProfile()), false);
  assert.equal(
    hasPersonalizationSignal({ recentClusters: [{ cluster_id: 'x' }], followedTopics: [], followedSources: [] }),
    true
  );
});

test('toggleDeliveryPreference flips briefing delivery settings', () => {
  const storage = makeStorage();
  const first = toggleDeliveryPreference('morningBriefing', storage);
  assert.equal(first.morningBriefing, false);

  const loaded = loadDeliveryPreferences(storage);
  assert.equal(loaded.morningBriefing, false);
});

test('buildDeliveryDigest reflects follows and briefing headings', () => {
  const profile = {
    recentClusters: [],
    followedTopics: ['Политика'],
    followedSources: ['Телма'],
  };
  const prefs = { morningBriefing: true, breakingAlerts: true };
  const digest = buildDeliveryDigest(
    '## Што го движи денот\n### 1. Собрание\n## Каде се разликува известувањето',
    profile,
    prefs
  );

  assert.match(digest, /Следени теми: Политика\./);
  assert.match(digest, /Следени извори: Телма\./);
  assert.match(digest, /• Што го движи денот/);
});

test('saveSyncToken persists and clears token values', () => {
  const storage = makeStorage();
  assert.equal(saveSyncToken('abc-123', storage), 'abc-123');
  assert.equal(loadSyncToken(storage), 'abc-123');
  assert.equal(saveSyncToken('', storage), '');
  assert.equal(loadSyncToken(storage), '');
});

test('mergeSyncPayload unions follows and keeps newest recent clusters', () => {
  const storage = makeStorage();
  toggleFollowedValue('topic', 'Политика', storage);
  saveDeliveryPreferences({ morningBriefing: false, breakingAlerts: true, browserPermission: 'default' }, storage);
  recordClusterView(
    {
      cluster_id: 'local-1',
      title: 'Local',
      category: 'Политика',
      topic: 'Политика',
      primarySource: 'MIA',
      sources: ['MIA'],
      tags: ['Буџет'],
      viewedAt: '2026-04-05T10:00:00Z',
    },
    storage
  );

  const merged = mergeSyncPayload(
    {
      followedTopics: ['Економија'],
      followedSources: ['Телма'],
      recentClusters: [
        {
          cluster_id: 'remote-1',
          title: 'Remote',
          category: 'Економија',
          topic: 'Економија',
          primarySource: 'Телма',
          sources: ['Телма'],
          tags: ['Инфлација'],
          viewedAt: '2026-04-05T12:00:00Z',
        },
      ],
      deliveryPreferences: { morningBriefing: true, breakingAlerts: false, browserPermission: 'granted' },
    },
    storage
  );

  assert.deepEqual(merged.profile.followedTopics, ['Политика', 'Економија']);
  assert.deepEqual(merged.profile.followedSources, ['Телма']);
  assert.equal(merged.profile.recentClusters[0].cluster_id, 'remote-1');
  assert.equal(exportSyncPayload(storage).deliveryPreferences.morningBriefing, false);
});

test('getOnboardingProgress reflects setup steps and dismissal', () => {
  const storage = makeStorage();
  const initial = getOnboardingProgress(storage);
  assert.equal(initial.doneCount, 0);
  assert.equal(initial.shouldShow, true);

  recordClusterView({ cluster_id: 'c1', title: 'A', category: 'Политика', topic: 'Политика', primarySource: 'MIA', sources: ['MIA'], tags: [] }, storage);
  recordClusterView({ cluster_id: 'c2', title: 'B', category: 'Економија', topic: 'Економија', primarySource: 'Телма', sources: ['Телма'], tags: [] }, storage);
  toggleFollowedValue('topic', 'Политика', storage);
  toggleFollowedValue('topic', 'Економија', storage);
  toggleFollowedValue('source', 'Телма', storage);
  saveSyncToken('sync-123', storage);

  const progressed = getOnboardingProgress(storage);
  assert.equal(progressed.doneCount, 4);
  assert.equal(progressed.completed, true);

  const dismissed = dismissOnboarding(storage);
  assert.equal(dismissed.dismissed, true);
  assert.equal(createDefaultOnboardingState().dismissed, false);
});

test('buildFollowRecommendations suggests unread topics and sources from reading history', () => {
  const profile = {
    recentClusters: [
      { cluster_id: 'c1', topic: 'Политика', category: 'Политика', primarySource: 'Телма', sources: ['Телма'], tags: [] },
      { cluster_id: 'c2', topic: 'Економија', category: 'Економија', primarySource: 'Телма', sources: ['Телма', 'МИА'], tags: [] },
      { cluster_id: 'c3', topic: 'Политика', category: 'Политика', primarySource: 'МИА', sources: ['МИА'], tags: [] },
    ],
    followedTopics: ['Спорт'],
    followedSources: ['24 Вести'],
  };

  const recommendations = buildFollowRecommendations(profile, 3);
  assert.equal(recommendations.topics[0].value, 'Политика');
  assert.ok(recommendations.sources.some((item) => item.value === 'Телма'));
  assert.ok(recommendations.sources.some((item) => item.value === 'МИА'));
});

test('buildFollowRecommendations omits already followed repeated topics and sources', () => {
  const profile = {
    recentClusters: [
      { cluster_id: 'c1', topic: 'Политика', category: 'Политика', primarySource: 'МИА', sources: ['МИА'], tags: [] },
      { cluster_id: 'c2', topic: 'Политика', category: 'Политика', primarySource: 'МИА', sources: ['МИА'], tags: [] },
    ],
    followedTopics: ['Политика'],
    followedSources: ['МИА'],
  };

  const recommendations = buildFollowRecommendations(profile, 3);
  assert.deepEqual(recommendations.topics, []);
  assert.deepEqual(recommendations.sources, []);
});

test('suggestion analytics stores deduplicated impressions and follow conversions by surface', () => {
  const storage = makeStorage();

  recordSuggestionImpressions('home_rail', [
    { kind: 'topic', value: 'Политика' },
    { kind: 'source', value: 'Телма' },
  ], storage);
  recordSuggestionImpressions('home_rail', [
    { kind: 'topic', value: 'Политика' },
    { kind: 'source', value: 'Телма' },
  ], storage);
  recordSuggestionFollow('home_rail', 'topic', 'Политика', storage);

  const analytics = loadSuggestionAnalytics(storage);
  assert.equal(analytics.surfaces.home_rail.topic.impressions, 1);
  assert.equal(analytics.surfaces.home_rail.source.impressions, 1);
  assert.equal(analytics.surfaces.home_rail.topic.follows, 1);

  const summary = getSuggestionConversionSummary(storage);
  assert.equal(summary.surfaces[0].surface, 'home_rail');
  assert.equal(summary.surfaces[0].impressions, 2);
  assert.equal(summary.surfaces[0].follows, 1);
  assert.equal(summary.totals.by_kind.topic.follows, 1);
  assert.equal(summary.totals.by_kind.source.impressions, 1);
});

test('suggestion analytics tracks dismissals and starts from empty defaults', () => {
  const storage = makeStorage();
  assert.deepEqual(createDefaultSuggestionAnalytics().surfaces, {});

  recordSuggestionDismiss('onboarding', storage);
  const summary = getSuggestionConversionSummary(storage);

  assert.equal(summary.surfaces[0].surface, 'onboarding');
  assert.equal(summary.surfaces[0].dismissals, 1);
  assert.equal(summary.totals.dismissals, 1);
});
