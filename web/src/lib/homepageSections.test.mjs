import test from 'node:test';
import assert from 'node:assert/strict';

import { buildHomepageSections } from './homepageSections.ts';

function cluster(id, sourceCount, extra = {}) {
  return {
    cluster_id: id,
    articles: Array.from({ length: sourceCount }, (_, index) => ({
      title: `${id} article ${index}`,
      source: `Source ${index}`,
    })),
    ...extra,
  };
}

test('buildHomepageSections gives developing stories priority over analysis buckets', () => {
  const clusters = [
    cluster('lead', 3),
    cluster('support-1', 2),
    cluster('support-2', 2),
    cluster('support-3', 2),
    cluster('support-4', 2),
    cluster('developing-1', 3, { pluralism_score: 80, has_fact_check: true }),
    cluster('developing-2', 2, { pluralism_score: 75 }),
    cluster('developing-3', 5),
    cluster('developing-4', 2),
  ];

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: clusters.slice(1, 5),
    forYouClusters: [],
    feedClusters: clusters.slice(5),
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: true,
  });

  assert.deepEqual(
    sections.developmentsFeatured.map((item) => item.cluster_id),
    ['developing-1', 'developing-2', 'developing-3', 'developing-4'],
  );
  assert.equal(sections.developmentsCompact.length, 0);
});

test('buildHomepageSections caps homepage developments to four featured and two compact', () => {
  const clusters = [
    cluster('lead', 3),
    cluster('support-1', 2),
    cluster('support-2', 2),
    cluster('support-3', 2),
    ...Array.from({ length: 10 }, (_, index) => cluster(`developing-${index + 1}`, 3)),
  ];

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: clusters.slice(1, 4),
    forYouClusters: [],
    feedClusters: clusters.slice(4),
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: true,
  });

  assert.equal(sections.developmentsFeatured.length, 4);
  assert.equal(sections.developmentsCompact.length, 2);
});

test('buildHomepageSections keeps later analysis sections from being starved by compact developments', () => {
  const clusters = [
    cluster('lead', 3),
    cluster('support-1', 2),
    cluster('support-2', 2),
    cluster('support-3', 2),
    cluster('support-4', 2),
    cluster('developing-1', 2),
    cluster('developing-2', 2),
    cluster('developing-3', 2),
    cluster('developing-4', 2),
    cluster('developing-5', 2),
    cluster('developing-6', 2),
    cluster('consensus-after-featured', 5),
    cluster('perspective-after-featured', 2, { pluralism_score: 85 }),
    cluster('radar-after-featured', 2, { has_fact_check: true }),
  ];

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: clusters.slice(1, 5),
    forYouClusters: [],
    feedClusters: clusters.slice(5),
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: true,
  });

  assert.equal(sections.developmentsFeatured.length, 4);
  assert.deepEqual(sections.consensusClusters.map((item) => item.cluster_id), ['consensus-after-featured']);
  assert.deepEqual(sections.perspectivesClusters.map((item) => item.cluster_id), ['perspective-after-featured']);
  assert.deepEqual(sections.radarClusters.map((item) => item.cluster_id), ['radar-after-featured']);
  assert.equal(sections.developmentsCompact.length, 2);
});

test('buildHomepageSections uses API developing list when articles are compacted', () => {
  const clusters = [
    cluster('lead', 3),
    cluster('support-1', 2),
    cluster('support-2', 2),
    cluster('support-3', 2),
  ];
  const developingClusters = [
    { cluster_id: 'dev-1', source_count: 1, articles: [{ title: 'A', source: 'N1' }] },
    { cluster_id: 'dev-2', source_count: 1, articles: [{ title: 'B', source: 'RTS' }] },
  ];

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: clusters.slice(1),
    forYouClusters: [],
    feedClusters: [...developingClusters],
    developingClusters,
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: true,
  });

  assert.deepEqual(
    sections.developmentsFeatured.map((item) => item.cluster_id),
    ['dev-1', 'dev-2'],
  );
});

test('buildHomepageSections surfaces full filtered feed after lead and supporting band', () => {
  const clusters = Array.from({ length: 14 }, (_, index) => cluster(`story-${index}`, index === 0 ? 3 : 1));

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: [],
    forYouClusters: [],
    feedClusters: [],
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: false,
  });

  assert.deepEqual(
    sections.supportingClusters.map((item) => item.cluster_id),
    ['story-1', 'story-2', 'story-3'],
  );
  assert.equal(sections.forYouClusters.length, 0);
  assert.deepEqual(
    sections.developmentsFeatured.map((item) => item.cluster_id),
    ['story-4', 'story-5', 'story-6', 'story-7', 'story-8', 'story-9'],
  );
  assert.deepEqual(
    sections.developmentsCompact.map((item) => item.cluster_id),
    ['story-10', 'story-11', 'story-12', 'story-13'],
  );
});
test('buildHomepageSections requires higher pluralism for perspectives band', () => {
  const clusters = [
    cluster('lead', 3),
    cluster('support-1', 2),
    cluster('support-2', 2),
    cluster('support-3', 2),
    cluster('dev-1', 3),
    cluster('dev-2', 3),
    cluster('dev-3', 3),
    cluster('dev-4', 3),
    cluster('dev-5', 3),
    cluster('dev-6', 3),
    cluster('low-pluralism', 2, { pluralism_score: 48 }),
    cluster('high-pluralism', 2, { pluralism_score: 62 }),
  ];

  const sections = buildHomepageSections({
    clusters,
    leadCluster: clusters[0],
    supportingClusters: clusters.slice(1, 4),
    forYouClusters: [],
    feedClusters: clusters.slice(4),
    wireClusters: [],
    wireArticles: [],
    excludedClusterIds: [],
    isHomepage: true,
  });

  assert.deepEqual(sections.perspectivesClusters.map((item) => item.cluster_id), ['high-pluralism']);
  assert.equal(sections.supportingFeatured.length, 1);
  assert.equal(sections.supportingCompact.length, 2);
});
