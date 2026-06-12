import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeFocusEntitySurface } from './focusEntityNormalize.ts';

test('normalizeFocusEntitySurface maps known inflections', () => {
  assert.equal(normalizeFocusEntitySurface('srbije'), 'Srbija');
  assert.equal(normalizeFocusEntitySurface('zvezde'), 'Crvena zvezda');
});

test('normalizeFocusEntitySurface capitalizes unknown lowercase names', () => {
  assert.equal(normalizeFocusEntitySurface('novak đoković'), 'Novak đoković');
});

test('normalizeFocusEntitySurface tolerates empty input', () => {
  assert.equal(normalizeFocusEntitySurface(''), '');
  assert.equal(normalizeFocusEntitySurface('   '), '');
});
