import test from 'node:test';
import assert from 'node:assert/strict';

import {
    isSynthesisMetaParagraph,
    prepareSynthesisParagraph,
    splitNarrativeParagraphs,
    stripBareUrls,
} from './synthesisCopy.ts';

test('stripBareUrls removes cluster links from prose', () => {
    const text = 'Веста https://presek.mk/cluster/abc123-def продолжува.';
    assert.equal(stripBareUrls(text), 'Веста продолжува.');
});

test('isSynthesisMetaParagraph detects source-analysis paragraphs', () => {
    assert.equal(
        isSynthesisMetaParagraph('Повеќето медиумски извештаи се согласуваат околу бројот.', 'mk'),
        true,
    );
    assert.equal(
        isSynthesisMetaParagraph('ТМФ одржа јубилејна модна ревија.', 'mk'),
        false,
    );
});

test('splitNarrativeParagraphs separates story and meta', () => {
    const article = [
        'Lead paragraph.',
        'Second paragraph.',
        'Повеќето извори се согласуваат.',
    ].join('\n');

    const { story, meta } = splitNarrativeParagraphs(article, 'mk');
    assert.equal(story.length, 2);
    assert.equal(meta.length, 1);
});

test('prepareSynthesisParagraph scrubs boilerplate and urls together', () => {
    const text = 'Пораз 4:1, со ограничено јавно значење. https://presek.mk/cluster/abc';
    assert.equal(prepareSynthesisParagraph(text, 'mk'), 'Пораз 4:1');
});
