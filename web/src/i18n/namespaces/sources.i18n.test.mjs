import test from 'node:test';
import assert from 'node:assert/strict';
import { sources } from './sources.ts';

test('sources namespace has non-empty mk strings', () => {
  for (const key of Object.keys(sources.mk)) {
    assert.ok(sources.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
