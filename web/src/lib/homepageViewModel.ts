import type { NewsCluster } from '../types';
import { chooseClusterImage } from '../utils/imageSelection.ts';
import { getStoryPreviewText } from '../utils/textUtils.ts';
import { buildUnifiedFeedItems } from './unifiedFeed.ts';
import {
    buildHomepageSynthesisExcludeIds,
    filterSynthesisPicks,
    selectVisibleAnalysisBands,
} from './homepageLayout.ts';
import { buildLeadSignals, buildLeadStatus, getFirstArticle } from './homepageLeadSignals.ts';
import type { LeadStatus } from './homepageLeadSignals.ts';
import { buildHomepageSections } from './homepageSections.ts';
import { getClockTimeStr } from './newsTimeFormat.ts';
import type { HomepageDataState, HomepageFilters } from './homepageData.ts';
import {
    buildFocusEntities,
    buildHomepageFlags,
    buildLeadViewModel,
    loadHomepageData,
    parseHomepageFilters,
} from './homepageData.ts';

export type HomepageViewModel = {
    homepageFlags: ReturnType<typeof buildHomepageFlags>;
    focusEntities: ReturnType<typeof buildFocusEntities>;
    leadCluster: NewsCluster | null;
    leadVisual: ReturnType<typeof chooseClusterImage> | null;
    leadSummary: string;
    leadTitle: string;
    finalLeadSignal: string;
    leadTitleIsCyrillic: boolean;
    leadSummaryIsCyrillic: boolean;
    activeFilterLabel: string | null;
    pipelineBusy: boolean;
    hasPartialFeedContent: boolean;
    showEmptyState: boolean;
    supportingClusters: NewsCluster[];
    forYouClusters: NewsCluster[];
    feedClusters: NewsCluster[];
    wireClusters: NewsCluster[];
    excludedClusterIds: string[];
    displayedTrendingClusters: NewsCluster[];
    supportingFeatured: NewsCluster[];
    supportingCompact: NewsCluster[];
    consensusClusters: NewsCluster[];
    perspectivesClusters: NewsCluster[];
    radarClusters: NewsCluster[];
    developmentsFeatured: NewsCluster[];
    developmentsCompact: NewsCluster[];
    topWireArticles: import('./homepageSections').WireArticle[];
    unifiedFeedItems: ReturnType<typeof buildUnifiedFeedItems>;
    pluralismPct: number | null;
    showLeadHeroVisual: boolean;
    displayedSynthesisPicks: NewsCluster[];
    feedSynthesisTeaser: NewsCluster | null;
    feedSynthesisMoreCount: number;
    analysisBands: ReturnType<typeof selectVisibleAnalysisBands>;
    leadEvidenceItems: Array<{ label: string; value: string; detail: string }>;
    leadStatus: LeadStatus | null;
    perspectiveBandItems: Array<{
        href: string;
        title: string;
        preview: string;
        category: string;
        pluralism: number;
        sources: string[];
        extraSources: number;
    }>;
    radarBandItems: Array<{ href: string; title: string; preview: string; source: string }>;
    consensusBandItems: Array<{ href: string; title: string; preview: string; category: string }>;
    analysisBandLabels: {
        reporting: string;
        factsConfirmed: string;
        factCheckSource: string;
        portalFallback: string;
    };
    perspectiveTeaser: string;
    radarTeaser: string;
    consensusTeaser: string;
    analizaNavItems: Array<{ target: string; kicker: string; label: string; count: number }>;
    analysisOverviewItems: Array<{ label: string; value: string; note: string }>;
    showAnalysisLayers: boolean;
};

export function buildHomepageViewModel(options: {
    homepageState: HomepageDataState;
    isHomepage: boolean;
    isSimpleHomepage: boolean;
    lang: 'sr' | 'mk';
    filters: HomepageFilters;
    t: (key: string) => string;
    localePath: (path: string) => string;
}): HomepageViewModel {
    const { homepageState, isHomepage, isSimpleHomepage, lang, filters, t, localePath } = options;
    const showAnalysisLayers = isHomepage && !isSimpleHomepage;
    const { category, topic, entity, subcategory, q } = filters;
    const {
        clusters,
        globalClusters,
        trending,
        topEntities,
        stats,
        synthesisPicks,
        homepageLeadDisplay,
        pipeline,
    } = homepageState;

    let supportingClusters = homepageState.supportingClusters;
    let forYouClusters = homepageState.forYouClusters;
    let feedClusters = homepageState.feedClusters;
    let wireClusters = homepageState.wireClusters;
    let excludedClusterIds = homepageState.excludedClusterIds;

    const homepageFlags = buildHomepageFlags(homepageState, isHomepage);
    const focusEntities = buildFocusEntities(topEntities);
    const leadCluster = homepageFlags.leadCluster;
    const leadVisual = leadCluster ? chooseClusterImage(leadCluster, 'hero', lang) : null;

    const {
        leadSummary,
        leadTitle,
        finalLeadSignal,
        leadTitleIsCyrillic,
        leadSummaryIsCyrillic,
    } = buildLeadViewModel({
        leadCluster,
        homepageLeadDisplay,
        isHomepage,
        lang,
        t,
    });

    const activeFilterLabel = subcategory || entity || category || topic || q || null;
    const pipelineBusy = homepageFlags.pipelineBusy;
    const hasPartialFeedContent = homepageFlags.hasPartialFeedContent;
    const showEmptyState = homepageFlags.showEmptyState;

    const homepageSections = buildHomepageSections({
        clusters,
        leadCluster,
        supportingClusters,
        forYouClusters,
        feedClusters,
        wireClusters,
        wireArticles: homepageState.wireArticles,
        excludedClusterIds,
        isHomepage,
    });

    ({
        supportingClusters,
        forYouClusters,
        feedClusters,
        wireClusters,
        excludedClusterIds,
    } = homepageSections);

    const {
        displayedTrendingClusters,
        supportingFeatured,
        supportingCompact,
        consensusClusters,
        perspectivesClusters,
        radarClusters,
        developmentsFeatured,
        developmentsCompact,
        topWireArticles,
    } = homepageSections;

    const unifiedFeedItems = isHomepage
        ? buildUnifiedFeedItems({
            developmentsFeatured,
            developmentsCompact,
            globalClusters,
            wireClusters,
        })
        : [];
    const pluralismPct = stats?.intelligence?.pluralism?.pluralism_pct ?? null;

    const showLeadHeroVisual = Boolean(leadVisual?.proxiedUrl);
    const displayedSynthesisPicks = isHomepage
        ? filterSynthesisPicks(synthesisPicks, buildHomepageSynthesisExcludeIds(leadCluster, supportingClusters))
        : synthesisPicks;
    const feedSynthesisTeaser = displayedSynthesisPicks[0] || null;
    const feedSynthesisMoreCount = Math.max(0, displayedSynthesisPicks.length - 1);
    const analysisBands = isHomepage
        ? selectVisibleAnalysisBands({
            radarCount: radarClusters.length,
            perspectivesCount: perspectivesClusters.length,
            consensusCount: consensusClusters.length,
        })
        : {
            radar: radarClusters.length > 0,
            perspectives: perspectivesClusters.length > 0,
            consensus: consensusClusters.length > 0,
        };

    const getTimeStr = (dateStr: string) => getClockTimeStr(dateStr, lang, {
        just_now: t('news.just_now'),
        ago: t('news.ago'),
        min_short: t('news.min_short'),
        hour: t('news.hour'),
        hours: t('news.hours'),
        day: t('news.day'),
        days: t('news.days'),
    });

    const leadFirstArticle = getFirstArticle(leadCluster);
    const leadLatestArticle = leadCluster?.articles?.[0] || null;
    const leadSignals = buildLeadSignals(leadCluster);
    const leadStatus = buildLeadStatus(leadCluster, lang);
    const leadUniqueSources = leadCluster
        ? Number((leadCluster as any).sources_count || (leadCluster as any).source_count || new Set(leadCluster.articles.map((article) => article.source).filter(Boolean)).size)
        : 0;

    const leadEvidenceItems = leadCluster ? [
        {
            label: lang === 'sr' ? 'Redakcije' : 'Редакции',
            value: String(leadUniqueSources),
            detail: leadCluster.articles.slice(0, 4).map((article) => article.source).filter(Boolean).join(' · '),
        },
        {
            label: lang === 'sr' ? 'Prva objava' : 'Прва објава',
            value: leadFirstArticle?.source || '',
            detail: leadFirstArticle ? getTimeStr(leadFirstArticle.ingested_at || leadFirstArticle.created_at) : '',
        },
        {
            label: lang === 'sr' ? 'Najnovije' : 'Најново',
            value: leadLatestArticle?.source || '',
            detail: leadLatestArticle ? getTimeStr(leadLatestArticle.ingested_at || leadLatestArticle.created_at) : '',
        },
        {
            label: lang === 'sr' ? 'Signal' : 'Сигнал',
            value: leadSignals[0] || leadLatestArticle?.category || '',
            detail: leadSignals.slice(1).join(' · '),
        },
    ].filter((item) => item.value) : [];

    const reportingLabel = lang === 'sr' ? 'Izveštavaju:' : 'Известуваат:';
    const factsConfirmedLabel = lang === 'sr' ? 'Činjenice potvrđene' : 'Фактите потврдени';
    const factCheckSourceLabel = lang === 'sr' ? 'Fakt-ček izvor:' : 'Факт-чек извор:';
    const portalFallbackLabel = lang === 'sr' ? 'Portal' : 'Портал';

    const perspectiveBandItems = perspectivesClusters.map((cluster: NewsCluster) => ({
        href: localePath(`/cluster/${cluster.cluster_id}`),
        title: cluster.synthetic_headline || cluster.articles?.[0]?.title || '',
        preview: getStoryPreviewText(cluster, cluster.articles?.[0], lang),
        category: cluster.articles?.[0]?.category || 'Tema',
        pluralism: cluster.pluralism_score || 50,
        sources: (cluster.articles || []).slice(0, 3).map((art) => art.source).filter(Boolean),
        extraSources: Math.max(0, (cluster.articles?.length || 0) - 3),
    }));

    const radarBandItems = radarClusters.map((cluster: NewsCluster) => {
        const factCheckedArticle = cluster.articles?.find((a) => a.is_fact_check) || cluster.articles?.[0];
        return {
            href: localePath(`/cluster/${cluster.cluster_id}`),
            title: cluster.synthetic_headline || factCheckedArticle?.title || '',
            preview: getStoryPreviewText(cluster, factCheckedArticle, lang),
            source: factCheckedArticle?.source || portalFallbackLabel,
        };
    });

    const consensusBandItems = consensusClusters.map((cluster: NewsCluster) => ({
        href: localePath(`/cluster/${cluster.cluster_id}`),
        title: cluster.synthetic_headline || cluster.articles?.[0]?.title || '',
        preview: getStoryPreviewText(cluster, cluster.articles?.[0], lang),
        category: cluster.articles?.[0]?.source || '',
    }));

    const analysisBandLabels = {
        reporting: reportingLabel,
        factsConfirmed: factsConfirmedLabel,
        factCheckSource: factCheckSourceLabel,
        portalFallback: portalFallbackLabel,
    };

    const perspectiveTeaser = perspectiveBandItems[0]?.title || '';
    const radarTeaser = radarBandItems[0]?.title || '';
    const consensusTeaser = consensusBandItems[0]?.title || '';

    const analizaNavItems: HomepageViewModel['analizaNavItems'] = [];
    if (displayedSynthesisPicks.length > 0) {
        analizaNavItems.push({
            target: '[data-synthesis-band]',
            kicker: lang === 'sr' ? 'Sinteza' : 'Синтеза',
            label: t('home.synthesis_picks_title'),
            count: displayedSynthesisPicks.length,
        });
    }
    if (displayedTrendingClusters.length > 0) {
        analizaNavItems.push({
            target: '[data-trending-strip]',
            kicker: t('home.trending'),
            label: lang === 'sr' ? 'Brzi pregled' : 'Брз преглед',
            count: displayedTrendingClusters.length,
        });
    }
    if (analysisBands.perspectives && perspectivesClusters.length > 0) {
        analizaNavItems.push({
            target: '[data-perspectives-band]',
            kicker: t('home.perspectives_title'),
            label: t('home.perspectives_subtitle'),
            count: perspectivesClusters.length,
        });
    }
    if (analysisBands.radar && radarClusters.length > 0) {
        analizaNavItems.push({
            target: '[data-radar-band]',
            kicker: t('home.radar_title'),
            label: t('home.radar_subtitle'),
            count: radarClusters.length,
        });
    }
    if (analysisBands.consensus && consensusClusters.length > 0) {
        analizaNavItems.push({
            target: '[data-consensus-band]',
            kicker: t('home.consensus_title'),
            label: t('home.consensus_subtitle'),
            count: consensusClusters.length,
        });
    }
    if (forYouClusters.length > 0) {
        analizaNavItems.push({
            target: '[data-for-you-band]',
            kicker: lang === 'sr' ? 'Za vas' : 'За вас',
            label: lang === 'sr' ? 'Personalizovano' : 'Персонализирано',
            count: forYouClusters.length,
        });
    }

    const analysisOverviewItems = [
        {
            label: t('home.analysis_overview_modules'),
            value: String(analizaNavItems.length),
            note: t('home.analysis_overview_modules_note'),
        },
        {
            label: t('home.analysis_overview_synthesis'),
            value: String(displayedSynthesisPicks.length),
            note: t('home.analysis_overview_synthesis_note'),
        },
        {
            label: t('home.analysis_overview_pluralism'),
            value: `${pluralismPct}%`,
            note: t('home.analysis_overview_pluralism_note'),
        },
        {
            label: t('home.analysis_overview_personal'),
            value: String(forYouClusters.length),
            note: t('home.analysis_overview_personal_note'),
        },
    ].filter((item) => item.value !== '0' || item.label === t('home.analysis_overview_pluralism'));

    return {
        homepageFlags,
        focusEntities,
        leadCluster,
        leadVisual,
        leadSummary,
        leadTitle,
        finalLeadSignal,
        leadTitleIsCyrillic,
        leadSummaryIsCyrillic,
        activeFilterLabel,
        pipelineBusy,
        hasPartialFeedContent,
        showEmptyState,
        supportingClusters,
        forYouClusters,
        feedClusters,
        wireClusters,
        excludedClusterIds,
        displayedTrendingClusters,
        supportingFeatured,
        supportingCompact,
        consensusClusters,
        perspectivesClusters,
        radarClusters,
        developmentsFeatured,
        developmentsCompact,
        topWireArticles,
        unifiedFeedItems,
        pluralismPct,
        showLeadHeroVisual,
        displayedSynthesisPicks,
        feedSynthesisTeaser,
        feedSynthesisMoreCount,
        analysisBands,
        leadEvidenceItems,
        leadStatus,
        perspectiveBandItems,
        radarBandItems,
        consensusBandItems,
        analysisBandLabels,
        perspectiveTeaser,
        radarTeaser,
        consensusTeaser,
        analizaNavItems,
        analysisOverviewItems,
        showAnalysisLayers,
    };
}

export async function loadHomepageViewModel(options: {
    apiUrl: string;
    lang: 'sr' | 'mk';
    searchParams: URLSearchParams;
    variant: 'feed' | 'pregled';
    fetchJson: (url: string) => Promise<any>;
    fetchJsonCached: (url: string) => Promise<any>;
    errorMessage: string;
    t: (key: string) => string;
    localePath: (path: string) => string;
}): Promise<HomepageViewModel & { homepageState: HomepageDataState; filters: HomepageFilters; error: string | null }> {
    const filters = parseHomepageFilters(options.searchParams);
    const isHomepage = filters.isHomepage;
    const isSimpleHomepage = isHomepage && options.variant !== 'pregled' && (
        options.searchParams.get('simple') === '1'
        || options.searchParams.get('view') === 'simple'
    );

    const homepageState = await loadHomepageData({
        apiUrl: options.apiUrl,
        lang: options.lang,
        searchParams: options.searchParams,
        fetchJson: options.fetchJson,
        fetchJsonCached: options.fetchJsonCached,
        errorMessage: options.errorMessage,
    });

    const viewModel = buildHomepageViewModel({
        homepageState,
        isHomepage,
        isSimpleHomepage,
        lang: options.lang,
        filters,
        t: options.t,
        localePath: options.localePath,
    });

    return {
        ...viewModel,
        homepageState,
        filters,
        error: homepageState.error,
    };
}
