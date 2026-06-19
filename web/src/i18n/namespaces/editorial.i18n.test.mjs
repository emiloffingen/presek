import test from 'node:test';
import assert from 'node:assert/strict';
import { editorial } from './editorial.ts';

test('editorial namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(editorial.sr).sort();
  const mkKeys = Object.keys(editorial.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk editorial namespaces must expose the same keys');
});

test('editorial namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(editorial.sr)) {
    assert.ok(editorial.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(editorial.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
