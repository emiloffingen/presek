import test from 'node:test';
import assert from 'node:assert/strict';
import { analize } from './analize.ts';

test('analize namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(analize.sr).sort();
  const mkKeys = Object.keys(analize.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk analize namespaces must expose the same keys');
});

test('analize namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(analize.sr)) {
    assert.ok(analize.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(analize.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
