import test from 'node:test';
import assert from 'node:assert/strict';
import { graph } from './graph.ts';

test('graph namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(graph.sr).sort();
  const mkKeys = Object.keys(graph.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk graph namespaces must expose the same keys');
});

test('graph namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(graph.sr)) {
    assert.ok(graph.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(graph.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
