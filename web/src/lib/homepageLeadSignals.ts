import type { NewsCluster } from '../types';
import { home } from '../i18n/namespaces/home.ts';

export type LeadStatusTone = 'live' | 'early' | 'consensus' | 'confirmed';

export interface LeadStatus {
  label: string;
  note: string;
  tone: LeadStatusTone;
}

type LeadLang = string;

function leadT(lang: LeadLang, key: string): string {
  const dict = (home[lang as keyof typeof home] || home.mk) as Record<string, string>;
  return dict[key] ?? key;
}

export function getFirstArticle(cluster: NewsCluster | null) {
  if (!cluster?.articles?.length) return null;
  return [...cluster.articles].sort((left, right) => {
    const leftTime = new Date(left.ingested_at || left.created_at).getTime();
    const rightTime = new Date(right.ingested_at || right.created_at).getTime();
    return leftTime - rightTime;
  })[0];
}

export function buildLeadStatus(cluster: NewsCluster | null, lang: LeadLang): LeadStatus | null {
  if (!cluster) return null;

  const uniqueSources = Number(
    (cluster as any).sources_count
    || (cluster as any).source_count
    || new Set(cluster.articles.map((article) => article.source).filter(Boolean)).size,
  );

  if (uniqueSources <= 1) {
    return {
      label: leadT(lang, 'home.lead_status_early_label'),
      note: leadT(lang, 'home.lead_status_early_note'),
      tone: 'early',
    };
  }

  if (uniqueSources >= 5) {
    return {
      label: leadT(lang, 'home.lead_status_consensus_label'),
      note: leadT(lang, 'home.lead_status_consensus_note'),
      tone: 'consensus',
    };
  }

  return {
    label: leadT(lang, 'home.lead_status_confirmed_label'),
    note: leadT(lang, 'home.lead_status_confirmed_note'),
    tone: 'confirmed',
  };
}

export function buildLeadSignals(cluster: NewsCluster | null): string[] {
  if (!cluster) return [];
  const leadLatestArticle = cluster.articles?.[0] || null;
  return Array.from(new Set([
    ...(cluster.analyst_entities || []),
    ...(cluster.tags || []),
    ...(cluster.topics || []),
    leadLatestArticle?.topic,
    leadLatestArticle?.category,
  ].filter(Boolean))).slice(0, 3) as string[];
}
