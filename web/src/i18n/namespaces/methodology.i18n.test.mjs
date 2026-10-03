import test from 'node:test';
import assert from 'node:assert/strict';
import { methodology } from './methodology.ts';

test('methodology namespace has non-empty mk strings', () => {
  for (const key of Object.keys(methodology.mk)) {
    assert.ok(methodology.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
