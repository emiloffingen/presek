import test from 'node:test';
import assert from 'node:assert/strict';
import { isStubFeedCluster } from './unifiedFeed.ts';

test('isStubFeedCluster flags thin single-source wire items', () => {
  assert.equal(
    isStubFeedCluster({
      cluster_id: 'stub',
      articles: [{ title: 'Канал 5', description: 'Министерката за енергетика...' }],
    }),
    true,
  );
});

test('isStubFeedCluster keeps substantive single-source stories', () => {
  assert.equal(
    isStubFeedCluster({
      cluster_id: 'full',
      articles: [{
        title: 'СДСМ предлага воведување на државни награди за Блаже Конески и Ремзи Несими',
        description: 'Пратеничката група на СДСМ поднесе предлог-закон за изменување на Законот за државни награди, со кој се предлага воведување на две нови државни награди.',
      }],
    }),
    false,
  );
});

test('isStubFeedCluster keeps multi-source clusters', () => {
  assert.equal(
    isStubFeedCluster({
      cluster_id: 'multi',
      articles: [{ title: 'A', description: 'x' }, { title: 'B', description: 'y' }],
    }),
    false,
  );
});
