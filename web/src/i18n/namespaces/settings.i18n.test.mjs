import test from 'node:test';
import assert from 'node:assert/strict';
import { settings } from './settings.ts';

test('settings namespace has non-empty mk strings', () => {
  for (const key of Object.keys(settings.mk)) {
    assert.ok(settings.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
