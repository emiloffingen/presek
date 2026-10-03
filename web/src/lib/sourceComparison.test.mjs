import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSourceRows, buildTrustView, hasComparisonContent } from './sourceComparison.ts';

test('buildSourceRows dedupes sources and keeps first-seen order', () => {
  const cluster = {
    articles: [
      { source: 'Telma', summary: 'A' },
      { source: 'Plusinfo', summary: 'B' },
      { source: 'Telma', summary: 'A again' },
      { source: 'A1on', summary: 'C' },
    ],
  };

  const rows = buildSourceRows(cluster);
  assert.deepEqual(rows.map((r) => r.name), ['Telma', 'Plusinfo', 'A1on']);
  assert.equal(rows[0].framing, 'A');
});

test('buildSourceRows skips missing/blank source names', () => {
  const cluster = {
    articles: [
      { source: '   ', summary: 'x' },
      { summary: 'y' },
      { source: 'MIA', summary: 'z' },
    ],
  };

  const rows = buildSourceRows(cluster);
  assert.deepEqual(rows.map((r) => r.name), ['MIA']);
});

test('buildSourceRows falls back to description and truncates long framing', () => {
  const long = 'збор '.repeat(40);
  const cluster = { articles: [{ source: 'Vecer', description: long }] };

  const rows = buildSourceRows(cluster);
  assert.equal(rows.length, 1);
  assert.ok(rows[0].framing.length <= 64, 'framing should be truncated');
  assert.ok(rows[0].framing.endsWith('…'));
});

test('buildSourceRows respects the row limit', () => {
  const cluster = {
    articles: Array.from({ length: 10 }, (_, i) => ({ source: `S${i}`, summary: 'x' })),
  };
  assert.equal(buildSourceRows(cluster, 3).length, 3);
});

test('buildSourceRows tolerates a missing articles array', () => {
  assert.deepEqual(buildSourceRows({}), []);
  assert.deepEqual(buildSourceRows({ articles: null }), []);
});

test('buildTrustView reads a full trust summary', () => {
  const view = buildTrustView({
    trust_summary: { score: 55, tier: 'consensus', label: 'Консензус', detail: 'd', sources_count: 3 },
  });
  assert.equal(view.score, 55);
  assert.equal(view.tier, 'consensus');
  assert.equal(view.label, 'Консензус');
  assert.equal(view.sourcesCount, 3);
});

test('buildTrustView falls back to source_count then article count', () => {
  assert.equal(buildTrustView({ source_count: 4 }, 9).sourcesCount, 4);
  assert.equal(buildTrustView({}, 9).sourcesCount, 9);
  assert.equal(buildTrustView({}).score, null);
});

test('hasComparisonContent is false for an empty cluster', () => {
  assert.equal(hasComparisonContent({}), false);
  assert.equal(hasComparisonContent({ articles: [{ source: 'MIA' }] }), true);
  assert.equal(hasComparisonContent({ trust_summary: { score: 10, label: 'X' } }), true);
});
