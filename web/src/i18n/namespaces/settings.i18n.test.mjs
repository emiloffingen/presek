import test from 'node:test';
import assert from 'node:assert/strict';
import { settings } from './settings.ts';

test('settings namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(settings.sr).sort();
  const mkKeys = Object.keys(settings.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk settings namespaces must expose the same keys');
});

test('settings namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(settings.sr)) {
    assert.ok(settings.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(settings.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
