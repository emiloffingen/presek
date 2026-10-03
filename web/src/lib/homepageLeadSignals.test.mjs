import assert from 'node:assert/strict';
import test from 'node:test';
import { buildLeadStatus } from './homepageLeadSignals.ts';

test('buildLeadStatus returns early signal for single-source clusters', () => {
  const status = buildLeadStatus({
    cluster_id: 'abc',
    articles: [{ source: 'A', title: 'Test' }],
  }, 'mk');

  assert.equal(status?.tone, 'early');
  assert.match(status?.label || '', /РАН СИГНАЛ/);
});
