import assert from 'node:assert/strict';
import test from 'node:test';
import { extractCleanSummaryText, getDisplaySummary, getStoryPreviewText, isSyntheticStandfirstBoilerplate, parseFootnotes, stripCitationMarkers } from '../utils/textUtils.ts';

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

test('parseFootnotes converts inline markers into anchor links', () => {
  const html = parseFootnotes('Potvrđeno u više medija [1] i [2, 3].');
  assert.match(html, /href="#citation-1"/);
  assert.match(html, /href="#citation-2"/);
  assert.match(html, /href="#citation-3"/);
  assert.match(html, /<sup class="citation-ref-wrap">/);
  assert.match(html, /aria-label="izvor 1"/);
  assert.doesNotMatch(html, />1<\/a>/);
});

test('extractCleanSummaryText unwraps truncated json summary blobs', () => {
  const leaked = '{"summary":"Izveštaj austrijskog dnevnika *Štandard* ukazuje na duboke veze';
  assert.equal(
    extractCleanSummaryText(leaked),
    'Izveštaj austrijskog dnevnika Štandard ukazuje na duboke veze',
  );
});

test('getDisplaySummary re-cleans leaked display_summary values', () => {
  const article = {
    display_summary: '{"summary":"Cisto rezime iz API sloja"}',
    summary: 'Fallback',
  };
  assert.equal(getDisplaySummary(article), 'Cisto rezime iz API sloja');
});
