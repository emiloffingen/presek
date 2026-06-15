import test from 'node:test';
import assert from 'node:assert/strict';

import { sanitizeHtml } from './sanitize.ts';
import { highlightScores, latToCyr, cyrToLat } from '../utils/textUtils.ts';

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

test('cyrToLat handles Serbian-specific letters and diacritics', () => {
  assert.equal(cyrToLat('Вучић'), 'Vučić');
  assert.equal(cyrToLat('Скопје'), 'Skopje');
  assert.equal(latToCyr('Đorđe'), 'Ѓорѓе');
  assert.equal(latToCyr('Niš'), 'Ниш');
});

test('script toggle round-trips Latin and Cyrillic content', () => {
  const latin = 'Beograd i Niš';
  const cyrillic = latToCyr(latin);
  assert.equal(cyrToLat(cyrillic), latin);
});
