import type { NewsCluster } from '../types';

type ClusterPools = {
    leadCluster: NewsCluster | null;
    supportingClusters: NewsCluster[];
    developmentsFeatured: NewsCluster[];
    developmentsCompact: NewsCluster[];
    displayedSynthesisPicks: NewsCluster[];
    unifiedFeedItems: Array<{ cluster: NewsCluster }>;
};

export type BroadsheetSections = {
    developing: NewsCluster[];
    picks: NewsCluster[];
    live: NewsCluster[];
};

/**
 * Fill the broadsheet's three cluster slots without repeating a story:
 * "Во развој" (rail, 5), "Синтези на денот" (4) and "Живо сега" (8).
 */
export function pickBroadsheetSections(pools: ClusterPools, limits = { developing: 5, picks: 4, live: 8 }): BroadsheetSections {
    const used = new Set<string>();
    if (pools.leadCluster?.cluster_id) used.add(pools.leadCluster.cluster_id);

    const take = (candidates: NewsCluster[], limit: number) => {
        const out: NewsCluster[] = [];
        for (const cluster of candidates) {
            if (out.length >= limit) break;
            if (!cluster?.cluster_id || used.has(cluster.cluster_id)) continue;
            if (!cluster.articles?.length) continue;
            used.add(cluster.cluster_id);
            out.push(cluster);
        }
        return out;
    };

    const feedClusters = pools.unifiedFeedItems.map((item) => item.cluster);
    const developing = take(
        [...pools.supportingClusters, ...pools.developmentsFeatured, ...pools.developmentsCompact],
        limits.developing,
    );
    const picks = take(pools.displayedSynthesisPicks, limits.picks);
    const live = take(feedClusters, limits.live);

    return { developing, picks, live };
}

type SourcePart = { source: string; count: number };

/**
 * Top `maxSources` sources plus "Други" for the rest. `other` is the article count the
 * caller already knows is outside `parts` (the API sends the top sources plus a remainder).
 */
export function foldSourceBreakdown(parts: SourcePart[], other = 0, maxSources = 3): SourcePart[] {
    const ranked = [...parts]
        .filter((part) => part?.source && part.count > 0)
        .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
    if (other <= 0 && ranked.length <= maxSources + 1) return ranked;
    const rest = ranked.slice(maxSources).reduce((sum, part) => sum + part.count, 0) + Math.max(0, other);
    return [...ranked.slice(0, maxSources), { source: 'Други', count: rest }];
}

/** Per-source article counts for the lead's coverage bar: top three plus "Други". */
export function buildSourceBreakdown(articles: Array<{ source?: string | null }>, maxSources = 3) {
    const counts = new Map<string, number>();
    for (const article of articles) {
        const source = String(article?.source || '').trim();
        if (!source) continue;
        counts.set(source, (counts.get(source) || 0) + 1);
    }
    return foldSourceBreakdown(
        [...counts.entries()].map(([source, count]) => ({ source, count })),
        0,
        maxSources,
    );
}

/**
 * Prefer the API's breakdown (computed over every article in the story); the shipped
 * `articles` are only a sample, so counting them under-reports big stories.
 */
export function clusterSourceBreakdown(cluster: any, maxSources = 3): SourcePart[] {
    const declared = cluster?.source_breakdown;
    if (Array.isArray(declared) && declared.length > 0) {
        return foldSourceBreakdown(declared, Number(cluster?.source_breakdown_other) || 0, maxSources);
    }
    return buildSourceBreakdown(cluster?.articles || [], maxSources);
}

const SECTION_LABELS_MK: Record<string, string> = {
    makedonija: 'Македонија',
    skopje: 'Скопје',
    balkan: 'Балкан',
    region: 'Регион',
    evropa: 'Европа',
    svet: 'Свет',
    amerika: 'Америка',
    azija: 'Азија',
    bliski_istok: 'Блиски Исток',
    kriminal: 'Криминал',
    hronika: 'Хроника',
    politika: 'Политика',
    ekonomija: 'Економија',
    sport: 'Спорт',
    kultura: 'Култура',
    zivot: 'Живот',
    tehnologija: 'Технологија',
    zdravje: 'Здравје',
    zabava: 'Забава',
    vesti: 'Вести',
};

/** Macedonian label for a backend category/topic code ("Kriminal" → "Криминал"); null when unknown. */
export function sectionLabelMk(raw: string | null | undefined): string | null {
    const key = String(raw || '').trim().toLowerCase().replace(/\s+/g, '_');
    if (!key) return null;
    return SECTION_LABELS_MK[key] || null;
}
