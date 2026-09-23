import test from 'node:test';
import assert from 'node:assert/strict';
import { pulse } from './pulse.ts';

test('pulse namespace has non-empty mk strings', () => {
  for (const key of Object.keys(pulse.mk)) {
    assert.ok(pulse.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
