import test from 'node:test';
import assert from 'node:assert/strict';
import { cluster } from './cluster.ts';

test('cluster namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(cluster.sr).sort();
  const mkKeys = Object.keys(cluster.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk cluster namespaces must expose the same keys');
});

test('cluster namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(cluster.sr)) {
    assert.ok(cluster.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(cluster.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
