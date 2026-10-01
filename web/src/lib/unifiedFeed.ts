import type { NewsCluster } from '../types';

export type FeedBucket = 'developing' | 'global' | 'wire';

export type UnifiedFeedItem = {
    cluster: NewsCluster;
    bucket: FeedBucket;
    variant: 'featured' | 'compact' | 'wire';
};

/** Single-source clusters with very little text read as wire stubs, not full cards. */
export function isStubFeedCluster(cluster: NewsCluster): boolean {
    const main = cluster.articles?.[0];
    if (!main) return true;

    const sources = Number(
        (cluster as any).sources_count || (cluster as any).source_count || cluster.articles?.length || 0,
    );
    if (sources >= 2) return false;

    const title = String(cluster.synthetic_headline || main.title || '').trim();
    const summary = String(main.summary || main.description || '').trim();

    if (title.length >= 48) return false;
    if (summary.length >= 90) return false;

    return title.length < 32 || summary.length < 48;
}

function clusterTrendScore(cluster: NewsCluster) {
    const sourceCount = Number((cluster as any).sources_count || (cluster as any).source_count || cluster.articles?.length || 0);
    return Number(cluster.homepage_score || 0)
        + Math.min(sourceCount, 8) * 5;
}

export function buildUnifiedFeedItems(input: {
    developmentsFeatured: NewsCluster[];
    developmentsCompact: NewsCluster[];
    globalClusters: NewsCluster[];
    wireClusters: NewsCluster[];
    excludeIds?: Iterable<string>;
}): UnifiedFeedItem[] {
    const seen = new Set<string>();
    for (const id of input.excludeIds || []) {
        if (id) seen.add(id);
    }
    const items: UnifiedFeedItem[] = [];

    const push = (cluster: NewsCluster, bucket: FeedBucket, variant: UnifiedFeedItem['variant']) => {
        if (!cluster?.cluster_id || seen.has(cluster.cluster_id)) return;
        if (variant === 'wire' && isStubFeedCluster(cluster)) return;
        seen.add(cluster.cluster_id);
        items.push({ cluster, bucket, variant });
    };

    input.developmentsFeatured.forEach((cluster) => push(cluster, 'developing', 'featured'));
    input.developmentsCompact.forEach((cluster) => push(cluster, 'developing', 'compact'));
    input.globalClusters.forEach((cluster, index) => push(cluster, 'global', index < 2 ? 'featured' : 'compact'));
    input.wireClusters.forEach((cluster) => push(cluster, 'wire', 'wire'));

    return items.sort((left, right) => clusterTrendScore(right.cluster) - clusterTrendScore(left.cluster));
}

export function countFeedBuckets(items: UnifiedFeedItem[]) {
    return items.reduce(
        (counts, item) => {
            counts[item.bucket] += 1;
            counts.all += 1;
            return counts;
        },
        { all: 0, developing: 0, global: 0, wire: 0 },
    );
}
