/**
 * Pure helpers for the homepage source-comparison panel.
 *
 * Kept framework-free so they can be unit-tested; the .astro component only
 * renders what these produce. Everything degrades gracefully when the cluster
 * has no trust summary or duplicated/missing source names.
 */

export interface SourceFramingRow {
  name: string;
  framing: string;
}

export interface TrustView {
  score: number | null;
  tier: string;
  label: string;
  detail: string;
  sourcesCount: number;
}

interface MinimalArticle {
  source?: string | null;
  summary?: string | null;
  description?: string | null;
}

interface MinimalCluster {
  articles?: MinimalArticle[] | null;
  reading_time?: number | null;
  source_count?: number | null;
  trust_summary?: {
    score?: number | null;
    tier?: string | null;
    label?: string | null;
    detail?: string | null;
    sources_count?: number | null;
  } | null;
}

const MAX_ROWS = 6;
const MAX_FRAMING = 64;

function compact(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * One row per distinct source, in first-seen order. Duplicates are dropped and
 * rows without a source name are skipped. Framing text is truncated on a word
 * boundary-ish so the row never overflows.
 */
export function buildSourceRows(cluster: MinimalCluster, limit = MAX_ROWS): SourceFramingRow[] {
  const articles = Array.isArray(cluster.articles) ? cluster.articles : [];
  const seen = new Set<string>();
  const rows: SourceFramingRow[] = [];

  for (const article of articles) {
    const name = compact(String(article?.source || ''));
    if (!name || seen.has(name)) continue;
    seen.add(name);

    const rawFraming = compact(String(article?.summary || article?.description || ''));
    const framing =
      rawFraming.length > MAX_FRAMING
        ? `${rawFraming.slice(0, MAX_FRAMING - 1).trimEnd()}…`
        : rawFraming;

    rows.push({ name, framing });
    if (rows.length >= limit) break;
  }

  return rows;
}

/**
 * Normalised verdict view. `score`/`label` are null-ish when the cluster has no
 * usable trust summary, so callers can hide the verdict block entirely.
 */
export function buildTrustView(cluster: MinimalCluster, fallbackSourceCount = 0): TrustView {
  const trust = cluster.trust_summary || {};
  const score = typeof trust.score === 'number' && Number.isFinite(trust.score) ? trust.score : null;
  const label = compact(String(trust.label || ''));
  const detail = compact(String(trust.detail || ''));
  const tier = compact(String(trust.tier || 'consensus')).toLowerCase() || 'consensus';

  const derivedCount =
    typeof trust.sources_count === 'number' && trust.sources_count > 0
      ? trust.sources_count
      : typeof cluster.source_count === 'number' && cluster.source_count > 0
        ? cluster.source_count
        : fallbackSourceCount;

  return { score, tier, label, detail, sourcesCount: derivedCount };
}

/** Whether the panel has anything worth rendering. */
export function hasComparisonContent(cluster: MinimalCluster): boolean {
  return buildSourceRows(cluster).length > 0 || buildTrustView(cluster).score !== null;
}
