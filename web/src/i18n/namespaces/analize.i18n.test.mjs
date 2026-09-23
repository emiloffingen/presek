import test from 'node:test';
import assert from 'node:assert/strict';
import { analize } from './analize.ts';

test('analize namespace has non-empty mk strings', () => {
  for (const key of Object.keys(analize.mk)) {
    assert.ok(analize.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
