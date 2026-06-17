import test from 'node:test';
import assert from 'node:assert/strict';
import { buildResearchQA } from './buildResearchQA.ts';

test('buildResearchQA maps facts, conflict and reactions from cluster data', () => {
  const items = buildResearchQA({
    lang: 'sr',
    questions: ['Q1', 'Q2', 'Q3'],
    keyFacts: ['Vlada je izdvojila 10 miliona evra.', 'Isplata pocinje u julu.'],
    perspectives: [
      { angle: 'Konflikt u izvorima', content: 'Jedan izvor naglasava hitnost, drugi oprez.' },
      { angle: 'Reakcije aktera', content: 'Opozicija traži bržu isplatu.' },
    ],
    synthesisBullets: ['[RTS] Vlada je potvrdila mere.'],
    generatedArticle: 'Glavni razvoj je potvrda novog paketa pomoći. Detalji slede tokom sedmice.',
    emptyAnswer: 'Nema dovoljno podataka.',
  });

  assert.equal(items.length, 3);
  assert.match(items[0].answer, /Konflikt|Glavni razvoj/i);
  assert.match(items[1].answer, /10 miliona/i);
  assert.match(items[2].answer, /Reakcije|Opozicija/i);
});

test('buildResearchQA hides empty answers upstream', () => {
  const items = buildResearchQA({
    lang: 'mk',
    questions: ['Q1', 'Q2', 'Q3'],
    emptyAnswer: 'Nema dovoljno podatoci.',
  });

  const visible = items.filter((item) => item.answer !== 'Nema dovoljno podatoci.');
  assert.equal(visible.length, 0);
});
