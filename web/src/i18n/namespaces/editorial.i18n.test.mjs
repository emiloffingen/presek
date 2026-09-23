import test from 'node:test';
import assert from 'node:assert/strict';
import { editorial } from './editorial.ts';

test('editorial namespace has non-empty mk strings', () => {
  for (const key of Object.keys(editorial.mk)) {
    assert.ok(editorial.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
