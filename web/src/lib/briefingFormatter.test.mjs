import test from 'node:test';
import assert from 'node:assert/strict';

import { formatBriefing, extractBriefingSections } from '../utils/briefingFormatter.ts';

const sample = `# **Naslov**

## Velika Slika
Prvi pasus velike slike.

## Ključne teme

**Požar u Enjubu [[d37b74072cad]]**
Tekst o požaru.

**Druga tema [[6c9807908894]]**
Drugi pasus.`;

test('formatBriefing renders bold item headlines as briefing-item-title', () => {
    const html = formatBriefing(sample, 'sr');

    assert.equal((html.match(/class="briefing-item-title"/g) || []).length, 2);
    assert.equal(html.includes('Požar u Enjubu'), true);
    assert.equal(html.includes('href="/cluster/d37b74072cad"'), true);
    assert.equal(html.includes('<p class="briefing-paragraph"><strong>Požar'), false);
});

test('formatBriefing uses editorial section headings without matrix labels', () => {
    const html = formatBriefing(sample, 'sr');

    assert.equal((html.match(/class="briefing-section-title"/g) || []).length, 2);
    assert.equal(html.includes('briefing-section-heading'), true);
    assert.equal(html.includes('<small>Sekcija</small>'), false);
    assert.equal(html.includes('<small>'), false);
});

test('extractBriefingSections keeps section titles from markdown', () => {
    const sections = extractBriefingSections(sample);

    assert.equal(sections.length, 2);
    assert.equal(sections[0].title, 'Velika Slika');
    assert.equal(sections[1].title, 'Ključne teme');
});
