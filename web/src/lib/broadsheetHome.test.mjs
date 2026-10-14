import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSourceBreakdown, clusterSourceBreakdown, pickBroadsheetSections, sectionLabelMk } from './broadsheetHome.ts';

const c = (id) => ({ cluster_id: id, articles: [{ title: id, source: 'S' }] });

test('pickBroadsheetSections never repeats the lead or a story across slots', () => {
  const sections = pickBroadsheetSections({
    leadCluster: c('lead'),
    supportingClusters: [c('lead'), c('a'), c('b')],
    developmentsFeatured: [c('c')],
    developmentsCompact: [],
    displayedSynthesisPicks: [c('a'), c('p1')],
    unifiedFeedItems: [{ cluster: c('b') }, { cluster: c('p1') }, { cluster: c('f1') }],
  });
  assert.deepEqual(sections.developing.map((x) => x.cluster_id), ['a', 'b', 'c']);
  assert.deepEqual(sections.picks.map((x) => x.cluster_id), ['p1']);
  assert.deepEqual(sections.live.map((x) => x.cluster_id), ['f1']);
});

test('pickBroadsheetSections respects limits and skips empty clusters', () => {
  const sections = pickBroadsheetSections({
    leadCluster: null,
    supportingClusters: [{ cluster_id: 'empty', articles: [] }, c('a'), c('b'), c('c')],
    developmentsFeatured: [],
    developmentsCompact: [],
    displayedSynthesisPicks: [],
    unifiedFeedItems: [],
  }, { developing: 2, picks: 4, live: 8 });
  assert.deepEqual(sections.developing.map((x) => x.cluster_id), ['a', 'b']);
});

test('buildSourceBreakdown ranks sources and folds the tail into Други', () => {
  const articles = ['A', 'A', 'B', 'C', 'D', 'E', ''].map((source) => ({ source }));
  assert.deepEqual(buildSourceBreakdown(articles), [
    { source: 'A', count: 2 },
    { source: 'B', count: 1 },
    { source: 'C', count: 1 },
    { source: 'Други', count: 2 },
  ]);
  assert.deepEqual(buildSourceBreakdown([{ source: 'A' }, { source: 'B' }]), [
    { source: 'A', count: 1 },
    { source: 'B', count: 1 },
  ]);
});

test('sectionLabelMk maps backend codes to Macedonian labels', () => {
  assert.equal(sectionLabelMk('Kriminal'), 'Криминал');
  assert.equal(sectionLabelMk('Amerika'), 'Америка');
  assert.equal(sectionLabelMk(''), null);
  assert.equal(sectionLabelMk('Nepoznato'), null);
});

test('clusterSourceBreakdown uses the API breakdown, not the 4-article sample', () => {
  const cluster = {
    // the payload only ships a sample of the story's articles...
    articles: [{ source: 'A' }, { source: 'B' }, { source: 'C' }, { source: 'D' }],
    // ...while the API counts every article
    source_breakdown: [
      { source: 'A', count: 9 },
      { source: 'B', count: 6 },
      { source: 'C', count: 4 },
      { source: 'D', count: 2 },
      { source: 'E', count: 1 },
    ],
    source_breakdown_other: 3,
  };
  assert.deepEqual(clusterSourceBreakdown(cluster), [
    { source: 'A', count: 9 },
    { source: 'B', count: 6 },
    { source: 'C', count: 4 },
    { source: 'Други', count: 6 },
  ]);
});

test('clusterSourceBreakdown folds the API remainder into Други even with few listed sources', () => {
  const cluster = { source_breakdown: [{ source: 'A', count: 2 }, { source: 'B', count: 1 }], source_breakdown_other: 5 };
  assert.deepEqual(clusterSourceBreakdown(cluster), [
    { source: 'A', count: 2 },
    { source: 'B', count: 1 },
    { source: 'Други', count: 5 },
  ]);
});

test('clusterSourceBreakdown falls back to the article sample when the API sends no breakdown', () => {
  assert.deepEqual(clusterSourceBreakdown({ articles: [{ source: 'A' }, { source: 'B' }] }), [
    { source: 'A', count: 1 },
    { source: 'B', count: 1 },
  ]);
});

test('hero image candidates are ascending and sizes names a slot for narrow and wide screens', async () => {
    const { HERO_IMAGE_WIDTHS, HERO_IMAGE_SIZES } = await import('./broadsheetHome.ts');
    assert.deepEqual([...HERO_IMAGE_WIDTHS], [...HERO_IMAGE_WIDTHS].sort((a, b) => a - b));
    assert.ok(HERO_IMAGE_WIDTHS.every((w) => w >= 320 && w <= 1200)); // the proxy clamps to 20..1200
    assert.match(HERO_IMAGE_SIZES, /max-width/);
});
