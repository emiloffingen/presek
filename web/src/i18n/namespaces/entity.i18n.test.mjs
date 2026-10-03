import test from 'node:test';
import assert from 'node:assert/strict';
import { entity } from './entity.ts';

test('entity namespace has non-empty mk strings', () => {
  for (const key of Object.keys(entity.mk)) {
    assert.ok(entity.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
