import test from 'node:test';
import assert from 'node:assert/strict';
import {
    buildHomepageFlags,
    cleanFilterParam,
    getBriefingSnippet,
    normalizeForYouCluster,
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
        for_you_pool: [{
            cluster_id: 'fy-1',
            articles: [{ title: 'A', source: 'RTS' }],
        }],
        synthesis_picks: [{ cluster_id: 'syn-1', articles: [] }],
        trending: [{ cluster_id: 't-1' }],
        focus_entities: [{ name: 'Vučić' }],
        stats: { intelligence: { pluralism: { pluralism_pct: 42 } } },
        briefing: { date: '2026-06-14' },
        lead_display: { title: 'Lead', summary: 'Summary.' },
        pipeline: { busy: true },
        excluded_cluster_ids: ['x-1'],
    });

    assert.equal(state.clusters.length, 6);
    assert.equal(state.supportingClusters.length, 1);
    assert.equal(state.forYouClusters.length, 1);
    assert.equal(state.forYouClusters[0].sources_count, 1);
    assert.equal(state.pipeline?.busy, true);
    assert.deepEqual(state.excludedClusterIds, ['x-1']);
});

test('normalizeForYouCluster keeps compact article fields for For You cards', () => {
    const cluster = normalizeForYouCluster({
        cluster_id: 'c1',
        is_breaking: true,
        topics: ['politics'],
        tags: ['tag'],
        homepage_score: 9,
        articles: [{ title: 'T', source: 'N1', summary: 'S', description: 'D', category: 'Cat' }, { title: 'T2' }],
    });

    assert.equal(cluster.cluster_id, 'c1');
    assert.equal(cluster.sources_count, 2);
    assert.equal(cluster.articles[0].source, 'N1');
});

test('buildHomepageFlags marks empty homepage as showEmptyState', () => {
    const flags = buildHomepageFlags({
        clusters: [],
        globalClusters: [],
        trending: [],
        topEntities: [],
        stats: null,
        briefing: null,
        error: null,
        supportingClusters: [],
        forYouClusters: [],
        feedClusters: [],
        wireClusters: [],
        wireArticles: [],
        excludedClusterIds: [],
        synthesisPicks: [],
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
        topEntities: [],
        stats: null,
        briefing: null,
        error: 'fail',
        supportingClusters: [],
        forYouClusters: [],
        feedClusters: [],
        wireClusters: [],
        wireArticles: [],
        excludedClusterIds: [],
        synthesisPicks: [],
        homepageLeadDisplay: null,
        pipeline: null,
    }, true);

    assert.equal(flags.shouldSetErrorStatus, true);
});

test('toLeadWhySentence returns first sentence trimmed to max length', () => {
    const long = 'Prva rečenica. Druga rečenica.';
    assert.equal(toLeadWhySentence(long), 'Prva rečenica.');
});

test('getBriefingSnippet extracts first paragraph from briefing markdown', () => {
    const snippet = getBriefingSnippet('## Šta pokreće dan\n\nGlavna vest dana.\n\n## Drugo');
    assert.equal(snippet, 'Glavna vest dana.');
});

test('cleanFilterParam returns null for blank values', () => {
    assert.equal(cleanFilterParam('   '), null);
    assert.equal(cleanFilterParam('## '), null);
});
