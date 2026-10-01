import type { NewsCluster } from '../types';

export type WireArticle = {
    cluster_id?: string;
    ingested_at?: string;
    created_at?: string;
    [key: string]: unknown;
};

type HomepageSectionsInput = {
    clusters: NewsCluster[];
    leadCluster: NewsCluster | null;
    supportingClusters: NewsCluster[];
    forYouClusters: any[];
    feedClusters: NewsCluster[];
    developingClusters?: NewsCluster[];
    wireClusters: NewsCluster[];
    wireArticles: WireArticle[];
    excludedClusterIds: string[];
    isHomepage: boolean;
    analysisClusters?: NewsCluster[];
};

function clusterSourceCount(cluster: NewsCluster) {
    return Number((cluster as any).source_count || (cluster as any).sources_count || cluster.articles?.length || 0);
}

function qualifiesAsContinuingCluster(cluster: NewsCluster) {
    return clusterSourceCount(cluster) >= 2 || (cluster.articles?.length || 0) >= 2;
}

function toForYouCluster(cluster: NewsCluster) {
    const article = cluster.articles?.[0] || {};
    const sourceCount = Number((cluster as any).sources_count || (cluster as any).source_count || cluster.articles?.length || 0);
    return {
        cluster_id: cluster.cluster_id,
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
        sources_count: sourceCount,
    };
}

function clusterTrendScore(cluster: NewsCluster) {
    const sourceCount = clusterSourceCount(cluster);
    return Number(cluster.homepage_score || 0)
        + Math.min(sourceCount, 8) * 5;
}

function sortByNewestArticle(left: WireArticle, right: WireArticle) {
    const leftTime = (left?.ingested_at || left?.created_at)
        ? new Date(left.ingested_at || left.created_at || '').getTime()
        : 0;
    const rightTime = (right?.ingested_at || right?.created_at)
        ? new Date(right.ingested_at || right.created_at || '').getTime()
        : 0;
    return rightTime - leftTime;
}

function dedupeWireArticles(wireArticles: WireArticle[]) {
    const uniqueRailIds = new Set<string>();
    const dedupedRailArticles: WireArticle[] = [];

    for (const article of wireArticles) {
        if (article.cluster_id && !uniqueRailIds.has(article.cluster_id)) {
            uniqueRailIds.add(article.cluster_id);
            dedupedRailArticles.push(article);
        } else if (!article.cluster_id) {
            dedupedRailArticles.push(article);
        }
    }

    return [...dedupedRailArticles].sort(sortByNewestArticle);
}

export function buildHomepageSections(input: HomepageSectionsInput) {
    const usedIds = new Set<string>();
    const leadId = input.leadCluster?.cluster_id;
    if (leadId) usedIds.add(leadId);

    let supportingClusters = input.supportingClusters;
    let forYouClusters = input.forYouClusters;
    let feedClusters = input.feedClusters;
    let wireClusters = input.wireClusters;
    let excludedClusterIds = input.excludedClusterIds;

    const analysisPool = Array.isArray(input.analysisClusters) && input.analysisClusters.length > 0
        ? input.analysisClusters
        : input.clusters;

    if (!input.isHomepage) {
        supportingClusters = input.clusters.slice(1, 4);
    }

    const filteredSupporting = supportingClusters
        .filter((cluster) => !usedIds.has(cluster.cluster_id))
        .slice(0, 3);
    const supportingFeatured = filteredSupporting.slice(0, 1);
    supportingFeatured.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const supportingCompact = filteredSupporting.slice(1).filter((cluster) => !usedIds.has(cluster.cluster_id));
    supportingCompact.forEach((cluster) => usedIds.add(cluster.cluster_id));

    if (!input.isHomepage) {
        forYouClusters = [];
        feedClusters = input.clusters.slice(4);
        wireClusters = [];
        excludedClusterIds = [
            leadId,
            ...supportingClusters.map((cluster) => cluster.cluster_id),
        ].filter(Boolean) as string[];
    }

    const continuingClusters = input.isHomepage && input.developingClusters?.length
        ? input.developingClusters.filter((cluster) => cluster?.cluster_id && !usedIds.has(cluster.cluster_id))
        : input.isHomepage
            ? feedClusters.filter(
                (cluster) => qualifiesAsContinuingCluster(cluster) && !usedIds.has(cluster.cluster_id),
            )
            : feedClusters.filter((cluster) => cluster?.cluster_id && !usedIds.has(cluster.cluster_id));
    const developmentsFeaturedLimit = input.isHomepage ? 4 : 6;
    const developmentsCompactLimit = input.isHomepage ? 2 : 12;
    const developmentsFeatured = continuingClusters.slice(0, developmentsFeaturedLimit);
    developmentsFeatured.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const developmentsCompact = continuingClusters
        .slice(developmentsFeaturedLimit, developmentsFeaturedLimit + developmentsCompactLimit)
        .filter((cluster) => !usedIds.has(cluster.cluster_id));
    developmentsCompact.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const consensusClusters = analysisPool
        .filter((cluster) => (cluster.articles?.length || 0) >= 4 && !usedIds.has(cluster.cluster_id))
        .slice(0, 3);
    consensusClusters.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const perspectivesClusters = analysisPool
        .filter((cluster) => (cluster.pluralism_score || 0) >= 55 && !usedIds.has(cluster.cluster_id))
        .sort((left, right) => (right.pluralism_score || 0) - (left.pluralism_score || 0))
        .slice(0, 3);
    perspectivesClusters.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const radarClusters = analysisPool
        .filter((cluster) => cluster.has_fact_check && !usedIds.has(cluster.cluster_id))
        .slice(0, 3);
    radarClusters.forEach((cluster) => usedIds.add(cluster.cluster_id));

    // Pick Trending clusters AFTER main sections are filled to ensure they get content in small locales
    const displayedTrendingClusters = Array.from(
        new Map(
            input.clusters
                .filter((cluster) =>
                    cluster?.cluster_id &&
                    !usedIds.has(cluster.cluster_id) &&
                    (cluster.articles?.length || 0) > 0
                )
                .sort((left, right) => clusterTrendScore(right) - clusterTrendScore(left))
                .map((cluster) => [cluster.cluster_id, cluster])
        ).values()
    ).slice(0, 6);
    displayedTrendingClusters.forEach((cluster) => usedIds.add(cluster.cluster_id));

    const railWireArticles = dedupeWireArticles(input.wireArticles);
    const topWireArticles = railWireArticles
        .filter((article) => article?.cluster_id && article.cluster_id !== leadId)
        .slice(0, 5);

    return {
        displayedTrendingClusters,
        supportingClusters,
        supportingFeatured,
        supportingCompact,
        consensusClusters,
        perspectivesClusters,
        radarClusters,
        forYouClusters,
        feedClusters,
        wireClusters,
        developmentsFeatured,
        developmentsCompact,
        railWireArticles,
        topWireArticles,
        excludedClusterIds,
    };
}
