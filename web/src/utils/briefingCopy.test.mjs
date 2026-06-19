import test from 'node:test';
import assert from 'node:assert/strict';

import {
    normalizeBriefingPayload,
    scrubBriefingBoilerplate,
    simplifyBriefingBullet,
} from './briefingCopy.ts';

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

test('scrubBriefingBoilerplate removes limited public significance phrasing', () => {
    const text = 'Пораз од Швајцарија со 4:1, со ограничено јавно значење.';
    assert.equal(
        scrubBriefingBoilerplate(text, 'mk'),
        'Пораз од Швајцарија со 4:1',
    );
});

test('simplifyBriefingBullet rewrites media emphasis bullets', () => {
    const bullet = 'За натпреварот меѓу Швајцарија и БиХ, медиумите нагласуваат на резултатот и значајноста на натпреварот.';
    assert.equal(
        simplifyBriefingBullet(bullet, 'mk'),
        'натпреварот меѓу Швајцарија и БиХ: резултатот и значајноста на натпреварот.',
    );
});
