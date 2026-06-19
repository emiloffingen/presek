import test from 'node:test';
import assert from 'node:assert/strict';
import { briefing } from './briefing.ts';

test('briefing namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(briefing.sr).sort();
  const mkKeys = Object.keys(briefing.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk briefing namespaces must expose the same keys');
});

test('briefing namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(briefing.sr)) {
    assert.ok(briefing.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(briefing.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
