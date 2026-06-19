import test from 'node:test';
import assert from 'node:assert/strict';
import { common } from './common.ts';

const forYouKeys = (locale) =>
  Object.keys(common[locale]).filter((key) => key.startsWith('for_you.')).sort();

test('for_you namespace has matching sr/mk keys', () => {
  assert.deepEqual(forYouKeys('mk'), forYouKeys('sr'), 'sr and mk for_you keys must match');
});

test('for_you namespace has no empty sr/mk strings', () => {
  for (const key of forYouKeys('sr')) {
    assert.ok(common.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(common.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
