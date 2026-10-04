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

/** Per-source article counts for the lead's coverage bar: top three plus "Други". */
export function buildSourceBreakdown(articles: Array<{ source?: string | null }>, maxSources = 3) {
    const counts = new Map<string, number>();
    for (const article of articles) {
        const source = String(article?.source || '').trim();
        if (!source) continue;
        counts.set(source, (counts.get(source) || 0) + 1);
    }
    const ranked = [...counts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([source, count]) => ({ source, count }));
    if (ranked.length <= maxSources + 1) return ranked;
    const rest = ranked.slice(maxSources).reduce((sum, part) => sum + part.count, 0);
    return [...ranked.slice(0, maxSources), { source: 'Други', count: rest }];
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
