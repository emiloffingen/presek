import test from 'node:test';
import assert from 'node:assert/strict';
import { archive } from './archive.ts';

test('archive namespace has non-empty mk strings', () => {
  for (const key of Object.keys(archive.mk)) {
    assert.ok(archive.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
