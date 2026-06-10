import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildHomepageSynthesisExcludeIds,
  filterSynthesisPicks,
  selectVisibleAnalysisBands,
} from './homepageLayout.ts';

test('filterSynthesisPicks removes lead and supporting duplicates', () => {
  const picks = [
    { cluster_id: 'lead', articles: [{ title: 'Lead' }] },
    { cluster_id: 'support-1', articles: [{ title: 'Support' }] },
    { cluster_id: 'pick-1', articles: [{ title: 'Pick' }] },
  ];

  const filtered = filterSynthesisPicks(picks, ['lead', 'support-1']);
  assert.deepEqual(filtered.map((item) => item.cluster_id), ['pick-1']);
});

test('selectVisibleAnalysisBands caps homepage analysis modules', () => {
  const bands = selectVisibleAnalysisBands({
    radarCount: 2,
    perspectivesCount: 3,
    consensusCount: 2,
    maxBands: 2,
  });

  assert.equal(bands.radar, true);
  assert.equal(bands.perspectives, true);
  assert.equal(bands.consensus, false);
});

test('buildHomepageSynthesisExcludeIds includes lead and supporting clusters', () => {
  assert.deepEqual(
    buildHomepageSynthesisExcludeIds(
      { cluster_id: 'lead', articles: [] },
      [{ cluster_id: 's1', articles: [] }, { cluster_id: 's2', articles: [] }],
    ),
    ['lead', 's1', 's2'],
  );
});
