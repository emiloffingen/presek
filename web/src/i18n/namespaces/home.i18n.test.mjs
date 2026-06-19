import test from 'node:test';
import assert from 'node:assert/strict';
import { home } from './home.ts';

test('home namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(home.sr).sort();
  const mkKeys = Object.keys(home.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk home namespaces must expose the same keys');
});

test('home namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(home.sr)) {
    assert.ok(home.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(home.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
