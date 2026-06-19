import test from 'node:test';
import assert from 'node:assert/strict';
import { resolvePlaceholderTint, PRESEK_MARK } from './placeholderTheme.ts';

test('resolvePlaceholderTint uses brand mark when dominant color is missing', () => {
  assert.equal(resolvePlaceholderTint(null), PRESEK_MARK);
  assert.equal(resolvePlaceholderTint(''), PRESEK_MARK);
});

test('resolvePlaceholderTint remaps legacy cold blue tints', () => {
  assert.equal(resolvePlaceholderTint('#1e40af'), PRESEK_MARK);
  assert.equal(resolvePlaceholderTint('#27272a'), PRESEK_MARK);
});

test('resolvePlaceholderTint keeps warm custom tints', () => {
  assert.equal(resolvePlaceholderTint('#b45309'), '#b45309');
});
