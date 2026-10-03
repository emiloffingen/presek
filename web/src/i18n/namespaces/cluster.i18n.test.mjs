import test from 'node:test';
import assert from 'node:assert/strict';
import { cluster } from './cluster.ts';

test('cluster namespace has non-empty mk strings', () => {
  for (const key of Object.keys(cluster.mk)) {
    assert.ok(cluster.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
