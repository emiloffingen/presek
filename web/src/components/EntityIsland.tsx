import React, { useEffect, useState } from 'react';
import {
  Building2,
  Link2,
  Loader2,
  Newspaper,
  Sparkles,
  TrendingUp,
  User,
} from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

interface EntityProfile {
  name: string;
  type: string;
  total_mentions: number;
  first_seen: string;
  last_seen: string;
  sentiment_score: number;
}

interface Relationship {
  related_entity: string;
  weight: number;
}

interface MediaStat {
  source: string;
  mention_count: number;
}

interface SentimentPoint {
  day: string;
  avg_sentiment: number;
  volume: number;
}

interface CategoryStat {
  category: string;
  count: number;
}

import type { NewsCluster } from '../types';

interface EntityPayload {
  profile: EntityProfile;
  related: Relationship[];
  media: MediaStat[];
  categories: CategoryStat[];
  sentiment_history: SentimentPoint[];
  clusters: NewsCluster[];
}

function formatDate(value?: string) {
  if (!value) return 'Непознато';
  try {
    return new Date(value).toLocaleDateString('mk-MK', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return 'Непознато';
  }
}

function formatRelative(value?: string) {
  if (!value) return 'неодамна';
  const now = new Date();
  const date = new Date(value);
  const diff = now.getTime() - date.getTime();
  const days = Math.max(0, Math.floor(diff / 86400000));
  if (days === 0) return 'денес';
  if (days === 1) return 'вчера';
  if (days < 7) return `пред ${days} дена`;
  return formatDate(value);
}

function sentimentLabel(score: number) {
  if (score >= 0.2) return 'Претежно позитивен';
  if (score <= -0.2) return 'Претежно критичен';
  return 'Главно неутрален';
}

function buildTimeline(history: SentimentPoint[]) {
  if (!history || !history.length) return [];
  const max = Math.max(1, ...history.map((item) => item.volume || 0));
  return history.map((item) => {
    const date = new Date(item.day);
    return {
      key: item.day,
      label: date.toLocaleDateString('mk-MK', { day: 'numeric', month: 'short' }),
      count: item.volume,
      percent: Math.max(8, Math.round((item.volume / max) * 100)),
      sentiment: item.avg_sentiment,
    };
  });
}

function getSentimentTrend(history: SentimentPoint[]) {
  if (!history || history.length < 2) return 'stable';
  const recent = history.slice(-3);
  const avg = recent.reduce((sum, item) => sum + item.avg_sentiment, 0) / recent.length;
  const prev = history.slice(-6, -3);
  if (prev.length === 0) return 'stable';
  const prevAvg = prev.reduce((sum, item) => sum + item.avg_sentiment, 0) / prev.length;
  
  if (avg > prevAvg + 0.1) return 'improving';
  if (avg < prevAvg - 0.1) return 'declining';
  return 'stable';
}

function splitRelated(related: Relationship[]) {
  if (!related.length) {
    return { strongest: [] as Relationship[], broader: [] as Relationship[] };
  }
  const maxWeight = Math.max(...related.map((item) => item.weight || 0), 1);
  const strongest = related.filter((item) => (item.weight || 0) >= maxWeight * 0.65).slice(0, 5);
  const strongestNames = new Set(strongest.map((item) => item.related_entity));
  const broader = related.filter((item) => !strongestNames.has(item.related_entity)).slice(0, 5);
  return { strongest, broader };
}

function buildWhyItMatters(profile: EntityProfile, clusters: NewsCluster[], related: Relationship[]) {
  const recentCount = clusters.length;
  if (recentCount >= 5) {
    return `${profile.name} е во силен фокус со ${recentCount} активни теми во последниот период, што укажува на висок јавен и медиумски интерес.`;
  }
  if (related.length >= 5) {
    return `${profile.name} се појавува во контекст на ${related.length} други клучни субјекти, градејќи комплексна мрежа на поврзаност во вестите.`;
  }
  return `Присуството на ${profile.name} во медиумите се следи преку анализа на тонот и фреквенцијата на споменување во реално време.`;
}

function coMentionedEntities(clusters: NewsCluster[], currentName: string) {
  const counts = new Map<string, number>();
  const current = currentName.toLowerCase();
  for (const cluster of clusters) {
    const ents = cluster.entities || []; 
    for (const entity of ents) {
      const clean = String(entity || '').trim();
      if (!clean || clean.toLowerCase() === current) continue;
      counts.set(clean, (counts.get(clean) || 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);
}

export default function EntityIsland({
  name,
  initialData = null,
}: {
  name: string;
  initialData?: EntityPayload | null;
}) {
  const [data, setData] = useState<EntityPayload | null>(initialData);
  const [loading, setLoading] = useState(!initialData);

  useEffect(() => {
    if (initialData) return;
    const API_URL = apiBaseUrl();
    fetch(`${API_URL}/intelligence/entity/${encodeURIComponent(name)}`)
      .then((res) => res.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name, initialData]);

  if (loading) {
    return (
      <div className="flex flex-col items-center py-20">
        <Loader2 className="animate-spin text-nyt-accent mb-4" size={32} />
        <p className="nyt-section-label text-muted-foreground">Ги подготвувам податоците...</p>
      </div>
    );
  }

  if (!data) return null;

  const { profile, related, media, categories, sentiment_history, clusters } = data;
  const timeline = buildTimeline(sentiment_history);
  const trend = getSentimentTrend(sentiment_history);
  const relationBands = splitRelated(related);
  const whyItMatters = buildWhyItMatters(profile, clusters, related);

  return (
    <div className="entity-flow">
      <header className="entity-hero">
        <div className="entity-hero-main">
          <div className="entity-badge">
            {profile.type === 'PERSON' ? <User size={32} className="text-nyt-accent" /> : <Building2 size={32} className="text-nyt-accent" />}
          </div>
          <div className="entity-copy">
            <span className="entity-type">{profile.type === 'ORG' ? 'Организација' : 'Субјект'}</span>
            <h1 className="entity-name">{profile.name}</h1>
            <p className="entity-summary-copy">
              Системски профил кој го следи медиумското присуство, мрежата на поврзаност и тонот на известување за {profile.name}.
            </p>
          </div>
        </div>

        <div className="entity-metrics">
          <div className="entity-metric">
            <p>Вкупно споменувања</p>
            <strong>{profile.total_mentions || clusters.length}</strong>
          </div>
          <div className="entity-metric">
            <p>Последно виден</p>
            <strong>{formatRelative(profile.last_seen || clusters[0]?.created_at)}</strong>
          </div>
          <div className="entity-metric">
            <p>Медиумски тон</p>
            <div className="flex flex-col">
                <strong className={profile.sentiment_score > 0.2 ? 'text-green-600' : profile.sentiment_score < -0.2 ? 'text-nyt-red' : 'text-nyt-accent'}>
                {sentimentLabel(profile.sentiment_score)}
                </strong>
                {trend !== 'stable' && (
                    <span className={`text-[9px] font-black uppercase tracking-tighter ${trend === 'improving' ? 'text-green-600' : 'text-nyt-red'}`}>
                        {trend === 'improving' ? '↑ Позитивен тренд' : '↓ Критички тренд'}
                    </span>
                )}
            </div>
          </div>
          <div className="entity-metric">
            <p>Поврзани субјекти</p>
            <strong>{related.length}</strong>
          </div>
        </div>
      </header>

      <div className="entity-grid">
        <div className="sources-main">
          <section className="entity-summary entity-featured">
            <h2 className="entity-section-title flex items-center gap-2"><Sparkles size={14} /> Медиумски Пресек</h2>
            <p className="entity-summary-copy">{whyItMatters}</p>
            <div className="entity-chip-list">
              <span className="entity-chip">{clusters.length} активни теми</span>
              <span className="entity-chip">{media.length} водечки медиуми</span>
              {categories && categories.length > 0 && (
                  <span className="entity-chip">Фокус: {categories[0].category}</span>
              )}
            </div>
          </section>

          <div className="entity-insight-grid">
            <section className="entity-summary">
              <div className="flex items-center justify-between mb-4">
                <h2 className="entity-section-title flex items-center gap-2 m-0"><TrendingUp size={14} /> Динамика</h2>
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Последни 14 дена</span>
              </div>
              <div className="entity-pulse h-32 flex items-end gap-1 px-2">
                {timeline.map((item) => (
                  <div key={item.key} className="flex-1 group relative">
                    <div 
                        className={`w-full rounded-t-sm transition-all ${item.sentiment > 0.1 ? 'bg-green-500/40' : item.sentiment < -0.1 ? 'bg-nyt-red/40' : 'bg-nyt-accent/40'} group-hover:opacity-100`} 
                        style={{ height: `${item.percent}%`, opacity: 0.7 }} 
                    />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-foreground text-background text-[9px] font-bold py-1 px-2 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none transition-opacity z-10">
                        {item.count} објави • {item.label}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-between mt-2 px-1 text-[9px] font-bold text-muted-foreground uppercase tracking-tighter">
                  <span>{timeline[0]?.label}</span>
                  <span>{timeline[Math.floor(timeline.length/2)]?.label}</span>
                  <span>{timeline[timeline.length-1]?.label}</span>
              </div>
            </section>

            <section className="entity-summary">
              <h2 className="entity-section-title flex items-center gap-2"><Newspaper size={14} /> Тематски Профил</h2>
              <div className="space-y-3 mt-4">
                {categories && categories.map((c) => (
                  <div key={c.category} className="flex items-center justify-between">
                    <span className="font-sans font-bold text-[11px] uppercase tracking-wide">{c.category}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-24 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-foreground opacity-80" 
                          style={{ width: `${Math.min((c.count / (clusters.length || 1)) * 100, 100)}%` }} 
                        />
                      </div>
                      <span className="font-sans text-[10px] font-black w-8 text-right">{Math.round((c.count / (clusters.length || 1)) * 100)}%</span>
                    </div>
                  </div>
                ))}
                {(!categories || categories.length === 0) && <p className="text-xs text-muted italic">Нема доволно податоци за теми.</p>}
              </div>
            </section>
          </div>

          <section className="entity-summary">
            <h2 className="entity-section-title flex items-center gap-2"><Link2 size={14} /> Истиот Контекст</h2>
            <div className="entity-chip-list">
              {coMentionedEntities(clusters, profile.name).map(([entity, count]) => (
                <a key={entity} href={`/subjekt/${encodeURIComponent(entity)}`} className="entity-chip entity-chip-link">
                  {entity} · {count}
                </a>
              ))}
              {coMentionedEntities(clusters, profile.name).length === 0 && (
                <div className="flex flex-wrap gap-2">
                  {related.map(r => (
                    <a key={r.related_entity} href={`/subjekt/${encodeURIComponent(r.related_entity)}`} className="entity-chip entity-chip-link">
                      {r.related_entity}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="sources-rail">
          <div className="rail-card">
            <h3 className="rail-card-title flex items-center gap-2"><Link2 size={14} /> Најтесно Поврзани</h3>
            <div className="space-y-4">
              {relationBands.strongest.map((rel) => (
                <a key={rel.related_entity} href={`/subjekt/${encodeURIComponent(rel.related_entity)}`} className="entity-related-link">
                  <div>
                    <span className="entity-related-name">{rel.related_entity}</span>
                    <p className="entity-related-band">Тесна врска</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="entity-related-track">
                      <div className="h-full bg-nyt-accent" style={{ width: `${Math.min(rel.weight * 10, 100)}%` }} />
                    </div>
                    <span className="entity-related-weight">{rel.weight}</span>
                  </div>
                </a>
              ))}
              {relationBands.strongest.length === 0 && <p className="text-xs text-muted italic">Нема пронајдени силни врски.</p>}
            </div>
          </div>

          <div className="rail-card rail-card-accent">
            <h3 className="rail-card-title">Автоматизиран надзор</h3>
            <p className="rail-copy">
              Овие податоци се генерираат преку постојано следење на македонскиот медиумски простор. Анализата на тонот и поврзаноста помага во разбирање на јавниот дискурс.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
