import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSourceBreakdown, pickBroadsheetSections, sectionLabelMk } from './broadsheetHome.ts';

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
