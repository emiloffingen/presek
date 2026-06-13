import test from 'node:test';
import assert from 'node:assert/strict';
import { buildUnifiedFeedItems, countFeedBuckets } from './unifiedFeed.ts';

test('buildUnifiedFeedItems dedupes clusters and assigns buckets', () => {
  const shared = { cluster_id: 'shared', homepage_score: 10, articles: [{ source: 'A' }, { source: 'B' }] };
  const items = buildUnifiedFeedItems({
    developmentsFeatured: [shared],
    developmentsCompact: [],
    globalClusters: [shared, { cluster_id: 'global-1', homepage_score: 5, articles: [{ source: 'B' }] }],
    wireClusters: [{ cluster_id: 'wire-1', homepage_score: 1, articles: [{ source: 'C', title: 'Договор меѓу САД и Иран близу финализација', description: 'Американскиот претседател изјави дека информациите што протекоа во јавноста немаат врска со условите што биле договорени.' }, { source: 'D', title: 'Wire follow-up', description: 'Second source keeps the wire item out of stub filtering.' }] }],
  });

  assert.equal(items.length, 3);
  assert.equal(items.find((item) => item.cluster.cluster_id === 'shared')?.bucket, 'developing');
  assert.deepEqual(countFeedBuckets(items), { all: 3, developing: 1, global: 1, wire: 1 });
});

test('buildUnifiedFeedItems sorts all items by trend score', () => {
  const items = buildUnifiedFeedItems({
    developmentsFeatured: [{ cluster_id: 'low', homepage_score: 1, articles: [{ source: 'A' }, { source: 'B' }] }],
    developmentsCompact: [],
    globalClusters: [{ cluster_id: 'high', homepage_score: 90, is_breaking: true, articles: [{ source: 'X' }] }],
    wireClusters: [],
  });

  assert.equal(items[0].cluster.cluster_id, 'high');
});

test('buildUnifiedFeedItems skips stub wire clusters', () => {
  const items = buildUnifiedFeedItems({
    developmentsFeatured: [],
    developmentsCompact: [],
    globalClusters: [],
    wireClusters: [
      { cluster_id: 'stub', homepage_score: 1, articles: [{ title: 'Канал 5', description: 'Министерката...' }] },
      {
        cluster_id: 'full',
        homepage_score: 2,
        articles: [{
          title: 'СДСМ предлага воведување на државни награди за Блаже Конески и Ремзи Несими',
          description: 'Пратеничката група на СДСМ поднесе предлог-закон за изменување на Законот за државни награди, со кој се предлага воведување на две нови државни награди.',
        }],
      },
    ],
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].cluster.cluster_id, 'full');
});
