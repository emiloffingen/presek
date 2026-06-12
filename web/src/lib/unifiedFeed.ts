import type { NewsCluster } from '../types';

export type FeedBucket = 'developing' | 'global' | 'wire';

export type UnifiedFeedItem = {
    cluster: NewsCluster;
    bucket: FeedBucket;
    variant: 'featured' | 'compact' | 'wire';
};

function clusterTrendScore(cluster: NewsCluster) {
    const sourceCount = Number((cluster as any).sources_count || (cluster as any).source_count || cluster.articles?.length || 0);
    return Number(cluster.homepage_score || 0)
        + (cluster.is_breaking ? 100 : 0)
        + Math.min(sourceCount, 8) * 5;
}

export function buildUnifiedFeedItems(input: {
    developmentsFeatured: NewsCluster[];
    developmentsCompact: NewsCluster[];
    globalClusters: NewsCluster[];
    wireClusters: NewsCluster[];
}): UnifiedFeedItem[] {
    const seen = new Set<string>();
    const items: UnifiedFeedItem[] = [];

    const push = (cluster: NewsCluster, bucket: FeedBucket, variant: UnifiedFeedItem['variant']) => {
        if (!cluster?.cluster_id || seen.has(cluster.cluster_id)) return;
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
