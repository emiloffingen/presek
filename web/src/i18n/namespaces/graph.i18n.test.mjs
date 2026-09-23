import test from 'node:test';
import assert from 'node:assert/strict';
import { graph } from './graph.ts';

test('graph namespace has non-empty mk strings', () => {
  for (const key of Object.keys(graph.mk)) {
    assert.ok(graph.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
