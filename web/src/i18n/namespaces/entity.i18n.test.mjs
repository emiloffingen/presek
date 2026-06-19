import test from 'node:test';
import assert from 'node:assert/strict';
import { entity } from './entity.ts';

test('entity namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(entity.sr).sort();
  const mkKeys = Object.keys(entity.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk entity namespaces must expose the same keys');
});

test('entity namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(entity.sr)) {
    assert.ok(entity.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(entity.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
