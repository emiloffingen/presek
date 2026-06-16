import { cleanAndDecode, normalizeEntityOrTag } from '../utils/textUtils';
import { buildTopicConnections } from './topicDiscovery.js';

export const TOPIC_QUERY_MAP: Record<string, { primary: 'topic' | 'category'; secondary?: 'topic' | 'category' }> = {
  Politika: { primary: 'topic', secondary: 'category' },
  Ekonomija: { primary: 'topic', secondary: 'category' },
  Svet: { primary: 'category', secondary: 'topic' },
  Sport: { primary: 'topic', secondary: 'category' },
  Tehnologija: { primary: 'topic', secondary: 'category' },
  Zabava: { primary: 'topic', secondary: 'category' },
};

export function parseTopicParam(raw: string | undefined) {
  const value = raw || '';
  try {
    return decodeURIComponent(value).replace(/\s+/g, ' ').trim();
  } catch {
    return value.replace(/\s+/g, ' ').trim();
  }
}

export function parseSynthesisLines(text?: string) {
  if (!text) return [];
  return String(cleanAndDecode(text))
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => line.trim().replace(/^[-•]\s+/, ''))
    .filter(Boolean)
    .filter((line) => line.toLowerCase() !== 'clanci:')
    .map((line) => line.replace(/^\[[^\]]+\]:\s*/, '').trim())
    .filter(Boolean);
}

export function normalizePerspectives(items: any[]) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const angle = String(item.angle ?? item.label ?? 'perspektiva').trim();
      const content = String(item.content ?? item.text ?? item.description ?? '').trim();
      if (!content) return null;
      return { angle: angle || 'perspektiva', content };
    })
    .filter(Boolean);
}

export function countTopicValues(values: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    const clean = String(value || '').trim();
    if (!clean) continue;
    counts.set(clean, (counts.get(clean) || 0) + 1);
  }
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
}

export function buildTopicNewsUrl(apiUrl: string, lang: 'sr' | 'mk', params: Record<string, string>) {
  const url = new URL(`${apiUrl}/news`);
  url.searchParams.set('page_size', '24');
  if (lang === 'mk') url.searchParams.set('lang', 'mk');
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return url.toString();
}

export async function loadTopicPageData({
  apiUrl,
  lang,
  topic,
  fetchJson,
}: {
  apiUrl: string;
  lang: 'sr' | 'mk';
  topic: string;
  fetchJson: (url: string) => Promise<any>;
}) {
  const queryPlan = TOPIC_QUERY_MAP[topic] || { primary: 'topic' as const, secondary: 'category' as const };
  let clusters: any[] = [];
  let error: string | null = null;
  const detailMap = new Map<string, any>();

  try {
    const primaryData = await fetchJson(buildTopicNewsUrl(apiUrl, lang, { [queryPlan.primary]: topic }));
    clusters = Array.isArray(primaryData?.clusters) ? primaryData.clusters : [];

    if (clusters.length === 0 && queryPlan.secondary && queryPlan.secondary !== queryPlan.primary) {
      const fallbackData = await fetchJson(buildTopicNewsUrl(apiUrl, lang, { [queryPlan.secondary]: topic }));
      clusters = Array.isArray(fallbackData?.clusters) ? fallbackData.clusters : [];
    }

    if (clusters.length > 0) {
      const ids = clusters.slice(0, 6).map((cluster: any) => cluster.cluster_id);
      const suffix = lang === 'mk' ? '?lang=mk' : '';
      const detailResults = await Promise.allSettled(
        ids.map((id: string) => fetchJson(`${apiUrl}/cluster/${id}${suffix}`)),
      );
      detailResults.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value?.data) {
          detailMap.set(ids[index], result.value.data);
        }
      });
    }
  } catch (e: any) {
    error = lang === 'mk' ? 'Темата моментално не е достапна.' : 'Tema trenutno nije dostupna.';
    return { clusters, detailMap, error, status: e?.status || 500 };
  }

  const leadCluster = clusters[0] ?? null;
  const supportingClusters = clusters.slice(1, 4);
  const feedClusters = clusters.slice(4, 16);
  const leadDetail = leadCluster ? detailMap.get(leadCluster.cluster_id) || null : null;
  const totalReports = clusters.reduce((sum: number, cluster: any) => sum + (cluster?.articles?.length || 0), 0);
  const uniqueSources = new Set(
    clusters.flatMap((cluster: any) => (cluster?.articles || []).map((article: any) => article?.source).filter(Boolean)),
  );
  const breakingCount = clusters.filter((cluster: any) => cluster?.is_breaking).length;
  const sourceRows = countTopicValues(
    clusters.flatMap((cluster: any) => (cluster?.articles || []).map((article: any) => article?.source)),
  ).slice(0, 6);
  const tagRows = countTopicValues(
    Array.from(detailMap.values())
      .flatMap((detail: any) => (Array.isArray(detail?.tags) ? detail.tags : []))
      .map((tag: string) => normalizeEntityOrTag(tag, lang)),
  )
    .filter(([name]) => name.toLowerCase() !== topic.toLowerCase())
    .slice(0, 8);

  const topicConnections = buildTopicConnections(topic, clusters.slice(0, 10), Array.from(detailMap.values()), 5);

  return {
    clusters,
    detailMap,
    error,
    status: 200,
    leadCluster,
    supportingClusters,
    feedClusters,
    leadDetail,
    featuredFeedClusters: feedClusters.slice(0, 4),
    compactFeedClusters: feedClusters.slice(4),
    totalReports,
    uniqueSources,
    breakingCount,
    sourceRows,
    tagRows,
    topicConnections,
    keyAngles: normalizePerspectives(leadDetail?.perspectives || []).slice(0, 3),
    synthesisLines: parseSynthesisLines(leadDetail?.synthesis || '').slice(0, 3),
    relatedClusters: Array.isArray(leadDetail?.related) ? leadDetail.related.slice(0, 4) : [],
  };
}

export function buildTopicIntro(
  topic: string,
  clusters: any[],
  uniqueSources: Set<string>,
  totalReports: number,
  breakingCount: number,
  lang: 'sr' | 'mk',
) {
  if (!clusters.length) return '';
  if (lang === 'mk') {
    if (breakingCount >= 2) {
      return `Темата ${topic} денес се развива брзо, со ${clusters.length} активни кластери и ${uniqueSources.size} извори што додаваат нови детали.`;
    }
    if (clusters.length >= 6) {
      return `Темата ${topic} е широко присутна низ денешниот циклус, со ${clusters.length} кластери и ${totalReports} извештаи што се надоврзуваат еден на друг.`;
    }
    return `Темата ${topic} останува релевантна денес, со ${clusters.length} кластери и повеќе редакции што ја следат од различни агли.`;
  }
  if (breakingCount >= 2) {
    return `Tema ${topic} se danas razvija brzo, sa ${clusters.length} aktivnih klastera i ${uniqueSources.size} izvora koji dodaju nove detalje.`;
  }
  if (clusters.length >= 6) {
    return `Tema ${topic} je široko prisutna kroz današnji ciklus, sa ${clusters.length} klastera i ${totalReports} izveštaja koji se nadovezuju jedan na drugi.`;
  }
  return `Tema ${topic} ostaje relevantna danas, sa ${clusters.length} klastera i više redakcija koje je prate iz različitih uglova.`;
}

export type TopicPageLabels = {
  kicker: string;
  contextTitle: string;
  contextOpen: string;
  noteLabel: string;
  statsClusters: string;
  statsSources: string;
  statsReports: string;
  statsBreaking: string;
  leadTitle: string;
  leadNote: string;
  anglesTitle: string;
  anglesNote: string;
  supportingTitle: string;
  supportingNote: string;
  feedTitle: string;
  feedNote: string;
  railContext: string;
  railOpen: string;
  tagsTitle: string;
  connectionsTitle: string;
  sourcesTitle: string;
  sourcesCountSuffix: string;
  relatedTitle: string;
  relatedCta: string;
  emptyBack: string;
  emptyArchive: string;
  emptyNoClusters: string;
  emptyHome: string;
  emptySearchArchive: string;
  sourceFollowReason: (count: number) => string;
  defaultLeadSummary: string;
};

export function buildTopicPageLabels(lang: 'sr' | 'mk'): TopicPageLabels {
  if (lang === 'mk') {
    return {
      kicker: 'Тема',
      contextTitle: 'Контекст на темата',
      contextOpen: 'ОТВОРИ',
      noteLabel: 'Што го движи овој простор',
      statsClusters: 'кластери',
      statsSources: 'извори',
      statsReports: 'Извештаи',
      statsBreaking: 'Во развој',
      leadTitle: 'Водечка приказна',
      leadNote: 'кластерот што најмногу ја носи темата напред во моментов.',
      anglesTitle: 'Каде се разликува покривањето',
      anglesNote: 'Главните агли што произлегуваат од водечкиот кластер во темата.',
      supportingTitle: 'Што се развива понатаму',
      supportingNote: 'Поврзани и следни кластери што ја прошируваат темата.',
      feedTitle: 'Повеќе од оваа тема',
      feedNote: 'Други активни кластери што вреди да останат во фокус.',
      railContext: 'Контекст и врски',
      railOpen: 'ОТВОРИ',
      tagsTitle: 'Имиња и агли',
      connectionsTitle: 'Каде понатаму',
      sourcesTitle: 'Извори што ја водат темата',
      sourcesCountSuffix: 'појавувања во кластерите',
      relatedTitle: 'Што да се чита понатаму',
      relatedCta: 'Отвори кластер',
      emptyBack: 'Назад на почеток',
      emptyArchive: 'Отвори архива',
      emptyNoClusters: 'Во моментов нема доволно активни кластери за оваа тема.',
      emptyHome: 'Почетна',
      emptySearchArchive: 'Пребарај во архива',
      sourceFollowReason: (count) => `${count} појавувања во активни кластери за оваа тема.`,
      defaultLeadSummary: 'Најсилните кластери во оваа тема се подредени според тежина, доверба и развој.',
    };
  }

  return {
    kicker: 'Tema',
    contextTitle: 'Kontekst teme',
    contextOpen: 'OTVORI',
    noteLabel: 'Šta pokreće ovaj prostor',
    statsClusters: 'klasteri',
    statsSources: 'izvori',
    statsReports: 'Izveštaji',
    statsBreaking: 'U razvoju',
    leadTitle: 'Vodeća priča',
    leadNote: 'klaster koji najviše nosi temu napred u ovom trenutku.',
    anglesTitle: 'Gde se razlikuje pokrivanje',
    anglesNote: 'Glavni uglovi koji proizlaze iz vodećeg klastera u temi.',
    supportingTitle: 'Šta se razvija dalje',
    supportingNote: 'Pridruženi i sledeći klasteri koji proširuju temu.',
    feedTitle: 'Više od ove teme',
    feedNote: 'Ostali aktivni klasteri koje vredi zadržati u vidnom polju.',
    railContext: 'Kontekst i veze',
    railOpen: 'OTVORI',
    tagsTitle: 'Imena i uglovi',
    connectionsTitle: 'Gde ići dalje',
    sourcesTitle: 'Izvori koji vode temu',
    sourcesCountSuffix: 'pojavljivanja u klasterima',
    relatedTitle: 'Šta čitati dalje',
    relatedCta: 'Otvori klaster',
    emptyBack: 'Nazad na početak',
    emptyArchive: 'Otvori arhivu',
    emptyNoClusters: 'Nema dovoljno aktivnih klastera za ovu temu u ovom trenutku.',
    emptyHome: 'Početna',
    emptySearchArchive: 'Potraži u arhivi',
    sourceFollowReason: (count) => `${count} pojavljivanja u aktivnim klasterima za ovu temu.`,
    defaultLeadSummary: 'Najsnažniji klasteri u ovoj temi su poređani po težini, poverenju i razvoju.',
  };
}

export function buildTopicPageMeta(lang: 'sr' | 'mk', topic: string) {
  if (lang === 'mk') {
    return {
      title: topic ? `${topic} | Тема` : 'Тема',
      description: `Активно за темата ${topic} — кластери, извори, перспективи и развој.`,
      breadcrumbTopics: 'Теми',
      siteUrl: 'https://presek.mk',
    };
  }

  return {
    title: topic ? `${topic} | Tema` : 'Tema',
    description: `još što je aktivno za temu ${topic} — klasteri, izvori, perspektive i razvoj.`,
    breadcrumbTopics: 'Teme',
    siteUrl: 'https://presek.live',
  };
}
