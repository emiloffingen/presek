import test from 'node:test';
import assert from 'node:assert/strict';
import { briefing } from './briefing.ts';

test('briefing namespace has non-empty mk strings', () => {
  for (const key of Object.keys(briefing.mk)) {
    assert.ok(briefing.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
