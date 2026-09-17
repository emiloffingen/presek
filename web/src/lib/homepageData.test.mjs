import test from 'node:test';
import assert from 'node:assert/strict';
import {
    buildHomepageFlags,
    cleanFilterParam,
    normalizeHomeApiResponse,
    parseHomepageFilters,
    toLeadWhySentence,
} from './homepageData.ts';

test('parseHomepageFilters returns isHomepage true when no filters', () => {
    const filters = parseHomepageFilters(new URLSearchParams(''));
    assert.equal(filters.isHomepage, true);
    assert.equal(filters.category, null);
});

test('parseHomepageFilters strips hash prefixes from filter params', () => {
    const filters = parseHomepageFilters(new URLSearchParams('category=%23Politika'));
    assert.equal(filters.category, 'Politika');
    assert.equal(filters.isHomepage, false);
});

test('parseHomepageFilters detects search query filter', () => {
    const filters = parseHomepageFilters(new URLSearchParams('q=Srbija'));
    assert.equal(filters.q, 'Srbija');
    assert.equal(filters.isHomepage, false);
});

test('normalizeHomeApiResponse maps home API payload into feed state', () => {
    const state = normalizeHomeApiResponse({
        lead: { cluster_id: 'lead-1', articles: [] },
        supporting: [{ cluster_id: 'sup-1', articles: [] }],
        developing: [{ cluster_id: 'dev-1', articles: [] }],
        wire: [{ cluster_id: 'wire-1', articles: [] }],
        trending: [{ cluster_id: 't-1' }],
        stats: { intelligence: { pluralism: { pluralism_pct: 42 } } },
        lead_display: { title: 'Lead', summary: 'Summary.' },
        pipeline: { busy: true },
        excluded_cluster_ids: ['x-1'],
    });

    assert.equal(state.clusters.length, 4);
    assert.equal(state.supportingClusters.length, 1);
    assert.equal(state.developingClusters.length, 1);
    assert.equal(state.pipeline?.busy, true);
    assert.deepEqual(state.excludedClusterIds, ['x-1']);
});

test('buildHomepageFlags marks empty homepage as showEmptyState', () => {
    const flags = buildHomepageFlags({
        clusters: [],
        globalClusters: [],
        trending: [],
        stats: null,
        error: null,
        supportingClusters: [],
        feedClusters: [],
        developingClusters: [],
        wireClusters: [],
        wireArticles: [],
        excludedClusterIds: [],
        homepageLeadDisplay: null,
        pipeline: null,
    }, true);

    assert.equal(flags.showEmptyState, true);
    assert.equal(flags.shouldSetErrorStatus, false);
});

test('buildHomepageFlags requests 500 when error and no partial content', () => {
    const flags = buildHomepageFlags({
        clusters: [],
        globalClusters: [],
        trending: [],
        stats: null,
        error: 'fail',
        supportingClusters: [],
        feedClusters: [],
        developingClusters: [],
        wireClusters: [],
        wireArticles: [],
        excludedClusterIds: [],
        homepageLeadDisplay: null,
        pipeline: null,
    }, true);

    assert.equal(flags.shouldSetErrorStatus, true);
});

test('toLeadWhySentence returns first sentence trimmed to max length', () => {
    const long = 'Prva rečenica. Druga rečenica.';
    assert.equal(toLeadWhySentence(long), 'Prva rečenica.');
});

test('cleanFilterParam returns null for blank values', () => {
    assert.equal(cleanFilterParam('   '), null);
    assert.equal(cleanFilterParam('## '), null);
});
