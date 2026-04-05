import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDeliveryDigest,
  buildPersonalizedClusters,
  createEmptyProfile,
  hasPersonalizationSignal,
  loadDeliveryPreferences,
  recordClusterView,
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
