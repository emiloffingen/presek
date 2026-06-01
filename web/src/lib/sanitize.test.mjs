import test from 'node:test';
import assert from 'node:assert/strict';

import { sanitizeHtml } from './sanitize.ts';
import { highlightScores, latToCyr } from '../utils/textUtils.ts';

test('sanitizeHtml strips attacker markup while preserving score highlighting markup', () => {
  const dirtyTitle = '<img src=x onerror=alert(1)> Победа 2:1';
  const rendered = sanitizeHtml(highlightScores(dirtyTitle));

  assert.equal(rendered.includes('<img'), false);
  assert.equal(rendered.includes('onerror'), false);
  assert.match(rendered, /<span class="font-bold text-red-600 dark:text-red-400">2:1<\/span>/);
});

test('latToCyr correctly transliterates vecer to вечер with correct casing', () => {
  assert.equal(latToCyr('Vecer'), 'Вечер');
  assert.equal(latToCyr('vecer'), 'вечер');
  assert.equal(latToCyr('VECER'), 'ВЕЧЕР');
  assert.equal(latToCyr('VEcer'), 'Вечер');
});
