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

interface EntityPayload {
  profile: EntityProfile;
  related: Relationship[];
  media: MediaStat[];
  clusters: any[];
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

function buildTimeline(clusters: any[]) {
  const days: { key: string; label: string; count: number }[] = [];
  const now = new Date();
  for (let offset = 5; offset >= 0; offset -= 1) {
    const date = new Date(now);
    date.setDate(now.getDate() - offset);
    const key = date.toISOString().slice(0, 10);
    days.push({
      key,
      label: date.toLocaleDateString('mk-MK', { weekday: 'short' }),
      count: 0,
    });
  }

  for (const cluster of clusters) {
    const createdAt = cluster.created_at;
    if (!createdAt) continue;
    const key = new Date(createdAt).toISOString().slice(0, 10);
    const day = days.find((item) => item.key === key);
    if (day) day.count += 1;
  }

  const max = Math.max(1, ...days.map((item) => item.count));
  return days.map((item) => ({
    ...item,
    percent: Math.max(8, Math.round((item.count / max) * 100)),
  }));
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

function buildWhyItMatters(profile: EntityProfile, clusters: any[], related: Relationship[]) {
  const recentCount = clusters.length;
  if (recentCount >= 5) {
    return `${profile.name} е во силен фокус со ${recentCount} активни теми во последниот период, што укажува на висок јавен и медиумски интерес.`;
  }
  if (related.length >= 5) {
    return `${profile.name} се појавува во контекст на ${related.length} други клучни субјекти, градејќи комплексна мрежа на поврзаност во вестите.`;
  }
  return `Присуството на ${profile.name} во медиумите се следи преку анализа на тонот и фреквенцијата на споменување во реално време.`;
}

export default function EntityIsland({
  name,
  initialClusters = [],
  initialData = null,
}: {
  name: string;
  initialClusters?: any[];
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

  const { profile, related, media, clusters } = data;
  const timeline = buildTimeline(clusters);
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
            <strong className={profile.sentiment_score > 0.2 ? 'text-green-600' : profile.sentiment_score < -0.2 ? 'text-nyt-red' : 'text-nyt-accent'}>
              {sentimentLabel(profile.sentiment_score)}
            </strong>
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
              <span className="entity-chip">{clusters.length} активни кластери</span>
              <span className="entity-chip">{media.length} водечки медиуми</span>
              {profile.first_seen && <span className="entity-chip">Прв пат во базата: {formatDate(profile.first_seen)}</span>}
            </div>
          </section>

          <div className="entity-insight-grid">
            <section className="entity-summary">
              <h2 className="entity-section-title flex items-center gap-2"><TrendingUp size={14} /> Динамика на појавување</h2>
              <div className="entity-pulse">
                {timeline.map((item) => (
                  <div key={item.key} className="entity-pulse-bar">
                    <span className="entity-pulse-count">{item.count}</span>
                    <div className="entity-pulse-track">
                      <div className="entity-pulse-fill" style={{ height: `${item.percent}%` }} />
                    </div>
                    <span className="entity-pulse-label">{item.label}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="entity-summary">
              <h2 className="entity-section-title flex items-center gap-2"><Newspaper size={14} /> Водечки медиуми</h2>
              <div className="space-y-4 mt-4">
                {media.map((m) => (
                  <div key={m.source} className="flex items-center justify-between">
                    <span className="font-serif font-bold text-sm">{m.source}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-24 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-nyt-accent" 
                          style={{ width: `${Math.min((m.mention_count / (clusters.length || 1)) * 100, 100)}%` }} 
                        />
                      </div>
                      <span className="font-sans text-[10px] font-black w-12 text-right">{m.mention_count} вести</span>
                    </div>
                  </div>
                ))}
                {media.length === 0 && <p className="text-xs text-muted italic">Нема доволно податоци за извори.</p>}
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

function coMentionedEntities(clusters: any[], currentName: string) {
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
