import test from 'node:test';
import assert from 'node:assert/strict';
import { archive } from './archive.ts';

test('archive namespace has matching sr/mk keys', () => {
  const srKeys = Object.keys(archive.sr).sort();
  const mkKeys = Object.keys(archive.mk).sort();
  assert.deepEqual(mkKeys, srKeys, 'sr and mk archive namespaces must expose the same keys');
});

test('archive namespace has no empty sr/mk strings', () => {
  for (const key of Object.keys(archive.sr)) {
    assert.ok(archive.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(archive.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
