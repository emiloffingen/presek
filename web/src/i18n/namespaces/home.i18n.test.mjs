import test from 'node:test';
import assert from 'node:assert/strict';
import { home } from './home.ts';

test('home namespace has non-empty mk strings', () => {
  for (const key of Object.keys(home.mk)) {
    assert.ok(home.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
