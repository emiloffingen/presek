import type { NewsCluster } from '../types';

export type AnalysisBandKind = 'radar' | 'perspectives' | 'consensus';

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
