import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizeBriefingPayload } from './briefingCopy.ts';

test('normalizeBriefingPayload preserves briefing markdown line breaks', () => {
    const markdown = '# **Naslov**\n\n## Velika Slika\nPrvi pasus.\n\n## Ključne teme\n\n**Tema**';
    const normalized = normalizeBriefingPayload({ status: 'success', content: markdown }, 'sr');

    assert.equal(normalized.content.includes('\n## Velika Slika'), true);
    assert.equal(normalized.content.includes('\n\n## Ključne teme'), true);
});

test('normalizeBriefingPayload still normalizes single-line briefing strings', () => {
    const normalized = normalizeBriefingPayload({ status: 'success', content: 'Brifing.' }, 'sr');
    assert.equal(normalized.content, 'Brifing.');
});
