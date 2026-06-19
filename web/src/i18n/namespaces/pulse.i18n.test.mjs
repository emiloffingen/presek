import test from 'node:test';
import assert from 'node:assert/strict';
import { pulse } from './pulse.ts';

test('pulse namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(pulse.sr).sort();
  const mkKeys = Object.keys(pulse.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk pulse namespaces must expose the same keys');
});

test('pulse namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(pulse.sr)) {
    assert.ok(pulse.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(pulse.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
