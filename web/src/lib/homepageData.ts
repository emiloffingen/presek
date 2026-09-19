import type { NewsCluster } from '../types';
import type { WireArticle } from './homepageSections';
import { prepareSynthesisParagraph } from '../utils/synthesisCopy.ts';
import {
    cleanAndDecode,
    extractCleanSummaryText,
    getStoryPreviewText,
    highlightScores,
    isMostlyCyrillic,
    isSyntheticStandfirstBoilerplate,
} from '../utils/textUtils.ts';

export type HomepageFilters = {
    category: string | null;
    topic: string | null;
    entity: string | null;
    subcategory: string | null;
    q: string | null;
    timespan: string | null;
    isHomepage: boolean;
};

export type HomepageLeadDisplay = {
    title?: string;
    summary?: string;
    signal?: string;
} | null;

export type HomepagePipeline = {
    busy?: boolean;
    intel_heavy_depth?: number;
} | null;

export type HomepageStats = {
    total_feeds?: number;
    last_24h?: number;
    intelligence?: {
        pluralism?: {
            pluralism_pct?: number;
        };
    };
    [key: string]: unknown;
};

export type HomepageDataState = {
    clusters: NewsCluster[];
    globalClusters: NewsCluster[];
    trending: unknown[];
    topEntities: unknown[];
    stats: HomepageStats | null;
    briefing: unknown | null;
    error: string | null;
    supportingClusters: NewsCluster[];
    forYouClusters: NewsCluster[];
    feedClusters: NewsCluster[];
    developingClusters: NewsCluster[];
    wireClusters: NewsCluster[];
    wireArticles: WireArticle[];
    excludedClusterIds: string[];
    synthesisPicks: NewsCluster[];
    homepageLeadDisplay: HomepageLeadDisplay;
    pipeline: HomepagePipeline;
};

export function cleanFilterParam(value: string | null): string | null {
    if (!value) return null;
    const cleaned = value
        .trim()
        .replace(/^[#\s]+/, '')
        .replace(/(?:\.{2,}|…)+$/u, '')
        .trim();
    return cleaned || null;
}

export function parseHomepageFilters(searchParams: URLSearchParams): HomepageFilters {
    const category = cleanFilterParam(searchParams.get('category'));
    const topic = cleanFilterParam(searchParams.get('topic'));
    const entity = cleanFilterParam(searchParams.get('entity'));
    const subcategory = cleanFilterParam(searchParams.get('subcategory'));
    const q = searchParams.get('q')?.trim() || null;
    const timespan = searchParams.get('timespan')?.trim() || null;
    const isHomepage = !(category || topic || entity || subcategory || q);

    return { category, topic, entity, subcategory, q, timespan, isHomepage };
}

export function normalizeForYouCluster(cluster: any): NewsCluster {
    const article = cluster.articles?.[0] || {};
    return ({
        cluster_id: cluster.cluster_id,
        is_breaking: cluster.is_breaking,
        topics: cluster.topics,
        tags: cluster.tags,
        homepage_score: cluster.homepage_score,
        articles: [{
            title: article.title,
            source: article.source,
            summary: article.summary,
            description: article.description,
            category: article.category,
        }],
        sources_count: cluster.articles?.length || 0,
    } as unknown) as NewsCluster;
}

export function normalizeBriefingPayload(payload: unknown) {
    if (!payload || typeof payload !== 'object') return null;
    const record = payload as { status?: string; content?: string };
    if (record.status !== 'success' || !record.content) return null;
    return payload;
}

export function normalizeHomeApiResponse(home: any): Omit<HomepageDataState, 'error'> {
    const lead = home?.lead ? [home.lead] : [];
    const supportingClusters = Array.isArray(home?.supporting) ? home.supporting : [];
    const forYouClusters = Array.isArray(home?.for_you_pool)
        ? home.for_you_pool.map(normalizeForYouCluster)
        : [];
    const developingClusters = Array.isArray(home?.developing) ? home.developing : [];
    const wireClusters = Array.isArray(home?.wire) ? home.wire : [];
    const wireArticles = (Array.isArray(home?.latest_wire) ? home.latest_wire : []) as WireArticle[];
    const globalClusters = Array.isArray(home?.global) ? home.global : [];
    const synthesisPicks = Array.isArray(home?.synthesis_picks) ? home.synthesis_picks : [];
    const feedClusters = [...developingClusters, ...wireClusters];

    return {
        clusters: [
            ...lead,
            ...supportingClusters,
            ...synthesisPicks,
            ...(Array.isArray(home?.for_you_pool) ? home.for_you_pool : []),
            ...feedClusters,
        ],
        globalClusters,
        trending: Array.isArray(home?.trending) ? home.trending : [],
        topEntities: Array.isArray(home?.focus_entities) ? home.focus_entities : [],
        stats: (home?.stats || null) as HomepageStats | null,
        briefing: normalizeBriefingPayload(home?.briefing),
        supportingClusters,
        forYouClusters,
        feedClusters,
        developingClusters,
        wireClusters,
        wireArticles,
        excludedClusterIds: Array.isArray(home?.excluded_cluster_ids) ? home.excluded_cluster_ids : [],
        synthesisPicks,
        homepageLeadDisplay: home?.lead_display && typeof home.lead_display === 'object' ? home.lead_display : null,
        pipeline: home?.pipeline && typeof home.pipeline === 'object' ? home.pipeline : null,
    };
}

export function emptyHomepageDataState(): HomepageDataState {
    return {
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
        developingClusters: [],
        wireClusters: [],
        wireArticles: [],
        excludedClusterIds: [],
        synthesisPicks: [],
        homepageLeadDisplay: null,
        pipeline: null,
    };
}

export async function loadHomepageFallback(options: {
    apiUrl: string;
    lang: string;
    fetchJson: (url: string) => Promise<any>;
    fetchJsonCached: (url: string) => Promise<any>;
}): Promise<{ state: HomepageDataState; recovered: boolean }> {
    const { apiUrl, lang, fetchJson, fetchJsonCached } = options;
    const state = emptyHomepageDataState();

    const fallbackNewsUrl = new URL(`${apiUrl}/news`);
    fallbackNewsUrl.searchParams.set('page_size', '24');
    fallbackNewsUrl.searchParams.set('lang', lang);
    fallbackNewsUrl.searchParams.set('sort', 'score');

    const [newsResult, trendResult, entityResult, statsResult, briefingResult, wireResult] = await Promise.allSettled([
        fetchJson(fallbackNewsUrl.toString()),
        fetchJsonCached(`${apiUrl}/trending?lang=${lang}`),
        fetchJsonCached(`${apiUrl}/intelligence/top-entities?limit=12&lang=${lang}`),
        fetchJsonCached(`${apiUrl}/stats/summary?lang=${lang}`),
        fetchJsonCached(`${apiUrl}/intelligence/briefing?lang=${lang}`),
        fetchJsonCached(`${apiUrl}/home/latest-wire?limit=15&lang=${lang}`),
    ]);

    if (newsResult.status === 'fulfilled') {
        state.clusters = Array.isArray(newsResult.value?.clusters) ? newsResult.value.clusters : [];
        state.globalClusters = Array.isArray(newsResult.value?.global_clusters) ? newsResult.value.global_clusters : [];
        state.supportingClusters = state.clusters.slice(1, 5);
        state.feedClusters = state.clusters.slice(5);
    }

    if (wireResult.status === 'fulfilled') {
        state.wireArticles = Array.isArray(wireResult.value?.articles) ? wireResult.value.articles : [];
    }

    state.trending = trendResult.status === 'fulfilled' && Array.isArray(trendResult.value)
        ? trendResult.value
        : [];
    state.topEntities = entityResult.status === 'fulfilled' && Array.isArray(entityResult.value)
        ? entityResult.value
        : [];
    state.stats = statsResult.status === 'fulfilled' ? statsResult.value : null;
    state.briefing = briefingResult.status === 'fulfilled'
        ? normalizeBriefingPayload(briefingResult.value)
        : null;

    const recovered = state.clusters.length > 0
        || state.wireArticles.length > 0
        || state.trending.length > 0;

    return { state, recovered };
}

export async function fetchFilteredNewsPayload(options: {
    apiUrl: string;
    lang: string;
    filters: HomepageFilters;
    fetchJson: (url: string) => Promise<any>;
    fetchJsonCached: (url: string) => Promise<any>;
    errorMessage: string;
}): Promise<HomepageDataState> {
    const { apiUrl, lang, filters, fetchJson, fetchJsonCached, errorMessage } = options;
    const state = emptyHomepageDataState();
    const { category, topic, entity, subcategory, q, timespan } = filters;

    const newsUrl = new URL(`${apiUrl}/news`);
    newsUrl.searchParams.set('page_size', '48');
    newsUrl.searchParams.set('lang', lang);
    if (category) newsUrl.searchParams.set('category', category);
    if (topic) newsUrl.searchParams.set('topic', topic);
    if (entity) newsUrl.searchParams.set('entity', entity);
    if (subcategory) newsUrl.searchParams.set('subcategory', subcategory);
    if (q) newsUrl.searchParams.set('q', q);
    if (timespan) newsUrl.searchParams.set('timespan', timespan);

    const [newsResult, trendResult, entityResult, statsResult, briefingResult] = await Promise.allSettled([
        fetchJson(newsUrl.toString()),
        fetchJsonCached(`${apiUrl}/trending?lang=${lang}`),
        fetchJsonCached(`${apiUrl}/intelligence/top-entities?limit=12&lang=${lang}`),
        fetchJsonCached(`${apiUrl}/stats/summary?lang=${lang}`),
        fetchJsonCached(`${apiUrl}/intelligence/briefing?lang=${lang}`),
    ]);

    if (newsResult.status === 'fulfilled') {
        state.clusters = newsResult.value?.clusters || [];
        state.globalClusters = newsResult.value?.global_clusters || [];
    } else {
        state.error = errorMessage;
    }

    state.trending = trendResult.status === 'fulfilled' && Array.isArray(trendResult.value)
        ? trendResult.value
        : [];
    state.topEntities = entityResult.status === 'fulfilled' && Array.isArray(entityResult.value)
        ? entityResult.value
        : [];
    state.stats = statsResult.status === 'fulfilled' ? statsResult.value : null;
    state.briefing = briefingResult.status === 'fulfilled'
        ? normalizeBriefingPayload(briefingResult.value)
        : null;

    return state;
}

export async function fetchHomepagePayload(options: {
    apiUrl: string;
    lang: string;
    fetchJson: (url: string) => Promise<any>;
    fetchJsonCached: (url: string) => Promise<any>;
    errorMessage: string;
}): Promise<HomepageDataState> {
    const { apiUrl, lang, fetchJson, fetchJsonCached, errorMessage } = options;
    const homePayload = await Promise.allSettled([
        fetchJson(`${apiUrl}/home?lang=${lang}`),
    ]).then(([result]) => result);

    if (homePayload.status === 'fulfilled' && homePayload.value?.status === 'success') {
        return { ...normalizeHomeApiResponse(homePayload.value), error: null };
    }

    const { state, recovered } = await loadHomepageFallback({
        apiUrl,
        lang,
        fetchJson,
        fetchJsonCached,
    });

    if (!recovered) {
        state.error = errorMessage;
    }

    return state;
}

export async function loadHomepageData(options: {
    apiUrl: string;
    lang: string;
    searchParams: URLSearchParams;
    fetchJson: (url: string) => Promise<any>;
    fetchJsonCached: (url: string) => Promise<any>;
    errorMessage: string;
}): Promise<HomepageDataState> {
    const filters = parseHomepageFilters(options.searchParams);

    if (filters.isHomepage) {
        return fetchHomepagePayload(options);
    }

    return fetchFilteredNewsPayload({
        ...options,
        filters,
    });
}

export function buildFocusEntities(topEntities: unknown[]) {
    return topEntities
        .map((ent: any) => ({
            ...ent,
            name: String(ent?.name || '').trim(),
            display_name: String(ent?.display_name || ent?.name || '').trim(),
        }))
        .filter((ent: { name: string }) => ent.name && ent.name.length >= 3)
        .slice(0, 10);
}

export function toLeadWhySentence(text: string, maxLen = 220): string {
    const trimmed = String(text || '').trim();
    if (!trimmed) return '';
    const sentenceMatch = trimmed.match(/^[^.!?…]+[.!?…]?/u);
    const sentence = (sentenceMatch?.[0] || trimmed).trim();
    return sentence.length > maxLen ? `${sentence.slice(0, maxLen - 1).trim()}…` : sentence;
}

export type LeadViewModel = {
    leadSignal: string;
    leadSummary: string;
    leadTitle: string;
    effectiveLeadSignal: string;
    finalLeadSignal: string;
    leadTitleIsCyrillic: boolean;
    leadSummaryIsCyrillic: boolean;
};

export function buildLeadViewModel(options: {
    leadCluster: NewsCluster | null;
    homepageLeadDisplay: HomepageLeadDisplay;
    isHomepage: boolean;
    lang: 'sr' | 'mk';
    t: (key: string) => string;
}): LeadViewModel {
    const { leadCluster, homepageLeadDisplay, isHomepage, lang, t } = options;

    const getLeadSignal = (cluster: NewsCluster) => {
        const count = cluster?.articles?.length || 0;
        if (cluster?.is_breaking) return t('home.lead_breaking');
        if (count >= 6) return t('home.lead_agenda');
        if (count >= 4) return t('home.lead_spreading');
        return t('home.lead_follow');
    };

    const leadSignal = leadCluster ? getLeadSignal(leadCluster) : '';
    const homepageLeadSummary = extractCleanSummaryText(homepageLeadDisplay?.summary || '');
    const leadSummary = prepareSynthesisParagraph(
        (isHomepage && homepageLeadSummary && !isSyntheticStandfirstBoilerplate(homepageLeadSummary)
            ? toLeadWhySentence(homepageLeadSummary)
            : (leadCluster
                ? toLeadWhySentence(getStoryPreviewText(leadCluster, leadCluster.articles?.[0], lang))
                : '')),
        lang,
    );
    const leadTitle = highlightScores(isHomepage
        ? String(homepageLeadDisplay?.title || '')
        : (leadCluster?.articles?.[0] ? cleanAndDecode(leadCluster.articles[0].title) : ''));
    const effectiveLeadSignal = isHomepage
        ? String(homepageLeadDisplay?.signal || leadSignal)
        : leadSignal;
    const finalLeadSignal = (
        effectiveLeadSignal === 'razvoj sto vredi da se sledi'
        || effectiveLeadSignal === 'развој што вреди да се следи'
        || effectiveLeadSignal === t('home.lead_follow')
    ) ? '' : effectiveLeadSignal;

    return {
        leadSignal,
        leadSummary,
        leadTitle,
        effectiveLeadSignal,
        finalLeadSignal,
        leadTitleIsCyrillic: isMostlyCyrillic(leadTitle),
        leadSummaryIsCyrillic: isMostlyCyrillic(leadSummary),
    };
}

export function buildHomepageFlags(state: HomepageDataState, isHomepage: boolean) {
    const leadCluster = state.clusters[0] ?? null;
    const hasPartialFeedContent = Boolean(
        leadCluster
        || state.supportingClusters.length > 0
        || state.wireArticles.length > 0
        || state.trending.length > 0
        || state.forYouClusters.length > 0
        || state.globalClusters.length > 0,
    );

    return {
        leadCluster,
        pipelineBusy: Boolean(state.pipeline?.busy),
        hasPartialFeedContent,
        showEmptyState: !hasPartialFeedContent,
        missingSystemModules: isHomepage && !state.error && hasPartialFeedContent && (!state.stats || !state.briefing),
        shouldSetErrorStatus: Boolean(
            state.error
            && !state.clusters.length
            && !state.wireArticles.length
            && !state.trending.length
            && !state.globalClusters.length,
        ),
    };
}

function trimBriefingSnippet(text: string, maxLen = 150) {
    const line = text
        .trim()
        .split('\n')
        .map((part) => part.replace(/\*\*/g, '').trim())
        .find(Boolean) || '';
    if (!line) return '';
    return line.length > maxLen ? `${line.substring(0, maxLen - 3)}...` : line;
}

export function getBriefingSnippet(content: string) {
    if (!content) return '';

    const legacy = content.match(/## Šta pokreće dan\n+([^#]+)/);
    if (legacy?.[1]) {
        return trimBriefingSnippet(legacy[1]);
    }

    const sectionBody = content.match(/^##\s+.+?\n+([^#]+)/m);
    if (sectionBody?.[1]) {
        return trimBriefingSnippet(sectionBody[1]);
    }

    const afterTitle = content.match(/^#\s+.+?\n+([^#]+)/m);
    if (afterTitle?.[1]) {
        return trimBriefingSnippet(afterTitle[1]);
    }

    return '';
}
