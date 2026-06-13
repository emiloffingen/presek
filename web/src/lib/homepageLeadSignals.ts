import type { NewsCluster } from '../types';

export type LeadStatusTone = 'live' | 'early' | 'consensus' | 'confirmed';

export interface LeadStatus {
  label: string;
  note: string;
  tone: LeadStatusTone;
}

export function getFirstArticle(cluster: NewsCluster | null) {
  if (!cluster?.articles?.length) return null;
  return [...cluster.articles].sort((left, right) => {
    const leftTime = new Date(left.ingested_at || left.created_at).getTime();
    const rightTime = new Date(right.ingested_at || right.created_at).getTime();
    return leftTime - rightTime;
  })[0];
}

export function buildLeadStatus(cluster: NewsCluster | null, lang: 'sr' | 'mk'): LeadStatus | null {
  if (!cluster) return null;

  const uniqueSources = Number(
    (cluster as any).sources_count
    || (cluster as any).source_count
    || new Set(cluster.articles.map((article) => article.source).filter(Boolean)).size,
  );

  if (cluster.is_breaking) {
    return {
      label: lang === 'sr' ? 'UŽIVO SE RAZVIJA' : 'СЕ РАЗВИВА ВО ЖИВО',
      note: lang === 'sr'
        ? 'Priča ima najjači trenutni signal u redakcijskom poretku.'
        : 'Приказната има најсилен тековен сигнал во уредничкиот редослед.',
      tone: 'live',
    };
  }

  if (uniqueSources <= 1) {
    return {
      label: lang === 'sr' ? 'RANI SIGNAL' : 'РАН СИГНАЛ',
      note: lang === 'sr'
        ? 'Trenutno dolazi iz jedne redakcije; pratimo da li se širi.'
        : 'Моментално доаѓа од една редакција; следиме дали ќе се прошири.',
      tone: 'early',
    };
  }

  if (uniqueSources >= 5) {
    return {
      label: lang === 'sr' ? 'ŠIROK KONSENZUS' : 'ШИРОК КОНСЕНЗУС',
      note: lang === 'sr'
        ? 'Više redakcija prati istu priču, što je čini glavnim signalom dana.'
        : 'Повеќе редакции ја следат истата приказна, што ја прави главен сигнал на денот.',
      tone: 'consensus',
    };
  }

  return {
    label: lang === 'sr' ? 'POTVRĐENO IZ VIŠE IZVORA' : 'ПОТВРДЕНО ОД ПОВЕЌЕ ИЗВОРИ',
    note: lang === 'sr'
      ? 'Klaster je povezan zajedničkom temom, akterima i vremenom objave.'
      : 'Кластерот е поврзан со заедничка тема, актери и време на објава.',
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
