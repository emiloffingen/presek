import assert from 'node:assert/strict';
import test from 'node:test';
import { getStoryPreviewText, isSyntheticStandfirstBoilerplate, stripCitationMarkers } from '../utils/textUtils.ts';

test('story previews skip generated standfirst boilerplate', () => {
  const cluster = {
    synthetic_standfirst: 'Уреднички преглед базиран на 21 извори...',
    articles: [
      {
        description: 'Ова е редовниот текст на приказната што треба да се прикаже.',
      },
    ],
  };

  assert.equal(isSyntheticStandfirstBoilerplate(cluster.synthetic_standfirst), true);
  assert.equal(
    getStoryPreviewText(cluster, cluster.articles[0], 'mk'),
    'Ова е редовниот текст на приказната што треба да се прикаже.'
  );
});

test('story previews keep meaningful synthetic standfirsts', () => {
  const cluster = {
    synthetic_standfirst: 'Партиите влегуваат во нов круг разговори по серија спротивставени изјави.',
    articles: [
      {
        description: 'Овој fallback не треба да се користи.',
      },
    ],
  };

  assert.equal(
    getStoryPreviewText(cluster, cluster.articles[0], 'mk'),
    'Партиите влегуваат во нов круг разговори по серија спротивставени изјави.'
  );
});

test('stripCitationMarkers removes comma-separated citation groups', () => {
  const input = 'Svi izvori se slažu oko toga [1,2,3,4]. Kolona je krenula u 11 sati [2, 4].';
  assert.equal(
    stripCitationMarkers(input),
    'Svi izvori se slažu oko toga. Kolona je krenula u 11 sati.'
  );
});

test('stripCitationMarkers removes single citation markers', () => {
  assert.equal(stripCitationMarkers('Potvrđeno u više medija [1].'), 'Potvrđeno u više medija.');
});
