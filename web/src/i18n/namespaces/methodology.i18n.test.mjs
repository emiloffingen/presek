import test from 'node:test';
import assert from 'node:assert/strict';
import { methodology } from './methodology.ts';

test('methodology namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(methodology.sr).sort();
  const mkKeys = Object.keys(methodology.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk methodology namespaces must expose the same keys');
});

test('methodology namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(methodology.sr)) {
    assert.ok(methodology.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(methodology.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
