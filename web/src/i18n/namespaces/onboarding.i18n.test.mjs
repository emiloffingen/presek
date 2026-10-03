import test from 'node:test';
import assert from 'node:assert/strict';
import { common } from './common.ts';

const keys = () => Object.keys(common.mk).filter((k) => k.startsWith('onboarding.')).sort();

test('common namespace has non-empty mk strings', () => {
  for (const key of keys()) {
    assert.ok(common.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
