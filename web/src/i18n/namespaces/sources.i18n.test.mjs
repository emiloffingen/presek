import test from 'node:test';
import assert from 'node:assert/strict';
import { sources } from './sources.ts';

test('sources namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(sources.sr).sort();
  const mkKeys = Object.keys(sources.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk sources namespaces must expose the same keys');
});

test('sources namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(sources.sr)) {
    assert.ok(sources.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(sources.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
