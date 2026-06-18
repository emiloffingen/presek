import assert from 'node:assert/strict';
import test from 'node:test';
import { renderSynthesisHtml } from './renderSynthesisHtml.ts';

test('renderSynthesisHtml strips numeric citation markers', () => {
  const html = renderSynthesisHtml('Potvrđeno u više medija [1] i [2, 3].');
  assert.equal(html, 'Potvrđeno u više medija i.');
  assert.doesNotMatch(html, /\[1\]/);
  assert.doesNotMatch(html, /citation-ref/);
});

test('renderSynthesisHtml converts markdown emphasis', () => {
  const html = renderSynthesisHtml('**Važno** i *nastavak* teksta.');
  assert.match(html, /<strong>Važno<\/strong>/);
  assert.match(html, /<em>nastavak<\/em>/);
});

test('renderSynthesisHtml removes AI placeholder text', () => {
  const html = renderSynthesisHtml('[PRETHODEN kontekst] Tekst nastavlja.');
  assert.equal(html, 'Tekst nastavlja.');
});
