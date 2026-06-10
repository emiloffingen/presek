import type { NewsCluster } from '../types';

export type AnalysisBandKind = 'radar' | 'perspectives' | 'consensus';

export function filterSynthesisPicks(
  picks: NewsCluster[],
  excludeIds: Iterable<string> = [],
): NewsCluster[] {
  const excluded = new Set(Array.from(excludeIds).filter(Boolean));
  return (picks || []).filter((pick) => pick?.cluster_id && !excluded.has(pick.cluster_id));
}

export function selectVisibleAnalysisBands(input: {
  radarCount: number;
  perspectivesCount: number;
  consensusCount: number;
  maxBands?: number;
}): Record<AnalysisBandKind, boolean> {
  const maxBands = input.maxBands ?? 2;
  const priority: AnalysisBandKind[] = [];

  if (input.radarCount > 0) priority.push('radar');
  if (input.perspectivesCount > 0) priority.push('perspectives');
  if (input.consensusCount > 0) priority.push('consensus');

  const visible = new Set(priority.slice(0, maxBands));
  return {
    radar: visible.has('radar'),
    perspectives: visible.has('perspectives'),
    consensus: visible.has('consensus'),
  };
}

export function buildHomepageSynthesisExcludeIds(
  leadCluster: NewsCluster | null,
  supportingClusters: NewsCluster[],
): string[] {
  return [
    leadCluster?.cluster_id,
    ...supportingClusters.map((cluster) => cluster.cluster_id),
  ].filter(Boolean) as string[];
}
