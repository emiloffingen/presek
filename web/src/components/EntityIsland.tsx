import React, { useEffect, useState } from 'react';
import {
  Building2,
  CalendarRange,
  Link2,
  Loader2,
  Newspaper,
  Sparkles,
  TrendingUp,
  User,
} from 'lucide-react';

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

interface ClusterArticle {
  title?: string;
  source?: string;
  created_at?: string;
  category?: string;
  description?: string;
  summary?: string;
}

interface ClusterItem {
  cluster_id: string;
  articles: ClusterArticle[];
  is_breaking?: boolean;
  has_synthesis?: boolean;
  entities?: string[];
}

interface EntityPayload {
  profile: EntityProfile;
  related: Relationship[];
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
  if (score >= 0.45) return 'Позитивен тон';
  if (score <= -0.45) return 'Негативен тон';
  return 'Мешан тон';
}

function uniqueSources(clusters: ClusterItem[]) {
  const seen = new Set<string>();
  for (const cluster of clusters) {
    for (const article of cluster.articles || []) {
      const source = String(article.source || '').trim();
      if (source) seen.add(source);
    }
  }
  return Array.from(seen);
}

function buildTimeline(clusters: ClusterItem[]) {
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
    const createdAt = cluster.articles?.[0]?.created_at;
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

function buildCategoryMix(clusters: ClusterItem[]) {
  const counts = new Map<string, number>();
  for (const cluster of clusters) {
    const category = String(cluster.articles?.[0]?.category || '').trim();
    if (!category) continue;
    counts.set(category, (counts.get(category) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
}

function buildCoMentionedEntities(clusters: ClusterItem[], currentName: string) {
  const counts = new Map<string, number>();
  const current = currentName.toLowerCase();
  for (const cluster of clusters) {
    for (const entity of cluster.entities || []) {
      const clean = String(entity || '').trim();
      if (!clean || clean.toLowerCase() === current) continue;
      counts.set(clean, (counts.get(clean) || 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
}

function getHighlights(clusters: ClusterItem[]) {
  return [...clusters]
    .sort((left, right) => {
      const leftLead = left.articles?.[0];
      const rightLead = right.articles?.[0];
      const leftScore =
        (left.has_synthesis ? 3 : 0) +
        (left.is_breaking ? 2 : 0) +
        ((left.articles || []).length >= 4 ? 1 : 0);
      const rightScore =
        (right.has_synthesis ? 3 : 0) +
        (right.is_breaking ? 2 : 0) +
        ((right.articles || []).length >= 4 ? 1 : 0);
      if (rightScore !== leftScore) return rightScore - leftScore;
      return new Date(rightLead?.created_at || 0).getTime() - new Date(leftLead?.created_at || 0).getTime();
    })
    .slice(0, 3);
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

function buildWhyItMatters(profile: EntityProfile, clusters: ClusterItem[], related: Relationship[]) {
  const recentClusters = clusters.filter((cluster) => {
    const createdAt = cluster.articles?.[0]?.created_at;
    if (!createdAt) return false;
    return Date.now() - new Date(createdAt).getTime() <= 72 * 3600 * 1000;
  }).length;
  const breakingCount = clusters.filter((cluster) => cluster.is_breaking).length;
  const synthesisCount = clusters.filter((cluster) => cluster.has_synthesis).length;
  const sourceCount = uniqueSources(clusters).length;

  if (breakingCount >= 1) {
    return `${profile.name} е повторно во фокус поради најмалку ${breakingCount} активни развои и ${recentClusters || 1} свежи кластери во последните три дена.`;
  }
  if (recentClusters >= 3) {
    return `${profile.name} се појавува во засилен краткорочен циклус: ${recentClusters} неодамнешни кластери, ${sourceCount} извори и ${synthesisCount} веќе издвоени синтези.`;
  }
  if (related.length >= 6) {
    return `${profile.name} е важен јазол во тековното известување затоа што се врзува со ${related.length} други релевантни имиња и теми, а не само со една изолирана вест.`;
  }
  return `${profile.name} останува релевантен преку континуирано појавување во повеќе извори, со јасно присуство во тековниот news cycle и во поврзаните приказни околу него.`;
}

export default function EntityIsland({
  name,
  initialClusters = [],
  initialData = null,
}: {
  name: string;
  initialClusters?: ClusterItem[];
  initialData?: EntityPayload | null;
}) {
  const [data, setData] = useState<EntityPayload | null>(initialData);
  const [loading, setLoading] = useState(!initialData);

  useEffect(() => {
    if (initialData) return;
    const API_URL = import.meta.env.PUBLIC_API_URL || (typeof window !== 'undefined' ? '/api' : 'http://127.0.0.1:5001/api');
    fetch(`${API_URL}/intelligence/entity/${encodeURIComponent(name)}`)
      .then((res) => res.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name, initialData]);

  if (loading) {
    return (
      <div className="flex flex-col items-center py-12">
        <Loader2 className="animate-spin text-accent" size={32} />
      </div>
    );
  }

  if (!data) return null;

  const { profile, related } = data;
  const timeline = buildTimeline(initialClusters);
  const categories = buildCategoryMix(initialClusters);
  const coMentioned = buildCoMentionedEntities(initialClusters, profile.name);
  const highlights = getHighlights(initialClusters);
  const sources = uniqueSources(initialClusters);
  const relationBands = splitRelated(related);
  const whyItMatters = buildWhyItMatters(profile, initialClusters, related);

  return (
    <div className="entity-flow">
      <header className="entity-hero">
        <div className="entity-hero-main">
          <div className="entity-badge">
            {profile.type === 'PERSON' ? <User size={32} className="text-accent" /> : <Building2 size={32} className="text-accent" />}
          </div>
          <div className="entity-copy">
            <span className="entity-type">{profile.type}</span>
            <h1 className="entity-name">{profile.name}</h1>
            <p className="entity-summary-copy">
              Профилот подолу го врзува тековното присуство на {profile.name} со поврзаните имиња, динамиката на споменувања и најрелевантните кластери.
            </p>
          </div>
        </div>

        <div className="entity-metrics">
          <div className="entity-metric">
            <p>Споменувања</p>
            <strong>{profile.total_mentions}</strong>
          </div>
          <div className="entity-metric">
            <p>Последно активен</p>
            <strong>{formatRelative(profile.last_seen)}</strong>
          </div>
          <div className="entity-metric">
            <p>Поврзани имиња</p>
            <strong>{related.length}</strong>
          </div>
          <div className="entity-metric">
            <p>Тон</p>
            <strong className="text-accent">{sentimentLabel(profile.sentiment_score)}</strong>
          </div>
        </div>
      </header>

      <div className="entity-grid">
        <div className="sources-main">
          <section className="entity-summary entity-featured">
            <h2 className="entity-section-title flex items-center gap-2"><Sparkles size={14} /> Зошто Е Важно Сега</h2>
            <p className="entity-summary-copy">{whyItMatters}</p>
            <div className="entity-chip-list">
              <span className="entity-chip">{initialClusters.length} кластери</span>
              <span className="entity-chip">{sources.length} извори</span>
              <span className="entity-chip">Прв пат виден {formatDate(profile.first_seen)}</span>
              <span className="entity-chip">Последно појавување {formatDate(profile.last_seen)}</span>
            </div>
          </section>

          <div className="entity-insight-grid">
            <section className="entity-summary">
              <h2 className="entity-section-title flex items-center gap-2"><TrendingUp size={14} /> Моментум</h2>
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
              <h2 className="entity-section-title flex items-center gap-2"><CalendarRange size={14} /> Во Што Се Појавува</h2>
              <div className="entity-chip-list">
                {categories.map(([category, count]) => (
                  <span key={category} className="entity-chip">{category} · {count}</span>
                ))}
                {categories.length === 0 && <span className="text-xs text-muted italic">Нема доволно категоризирани кластери.</span>}
              </div>
              <p className="rail-copy">
                Најчестите категории покажуваат дали {profile.name} моментално влегува во политичка, економска, меѓународна или поширока контекстуална приказна.
              </p>
            </section>
          </div>

          <section className="entity-summary">
            <h2 className="entity-section-title flex items-center gap-2"><Newspaper size={14} /> Кластери Во Фокус</h2>
            <div className="entity-highlight-list">
              {highlights.map((cluster) => {
                const lead = cluster.articles?.[0];
                if (!lead) return null;
                return (
                  <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="entity-highlight-link">
                    <div className="entity-highlight-meta">
                      <span>{lead.source || 'Извор'}</span>
                      <span className="dot">·</span>
                      <span>{formatRelative(lead.created_at)}</span>
                      <span className="dot">·</span>
                      <span>{(cluster.articles || []).length} извори</span>
                    </div>
                    <h3 className="entity-highlight-title">{lead.title}</h3>
                    <p className="entity-highlight-copy">
                      {cluster.has_synthesis
                        ? 'Кластерот веќе има синтеза и носи споредени извори, не само основен развој.'
                        : cluster.is_breaking
                        ? 'Овој кластер се развива како брза тема што вреди да се следи.'
                        : 'Овој кластер е корисен за контекстот и мрежата околу ентитетот.'}
                    </p>
                  </a>
                );
              })}
              {highlights.length === 0 && <p className="text-xs text-muted italic">Нема издвоени кластери за прикажување.</p>}
            </div>
          </section>

          <section className="entity-summary">
            <h2 className="entity-section-title flex items-center gap-2"><Link2 size={14} /> Истиот Контекст</h2>
            <div className="entity-chip-list">
              {coMentioned.map(([entity, count]) => (
                <a key={entity} href={`/entity/${encodeURIComponent(entity)}`} className="entity-chip entity-chip-link">
                  {entity} · {count}
                </a>
              ))}
              {coMentioned.length === 0 && <span className="text-xs text-muted italic">Нема доволно ко-споменувања во тековните кластери.</span>}
            </div>
          </section>
        </div>

        <aside className="sources-rail">
          <div className="rail-card">
            <h3 className="rail-card-title flex items-center gap-2"><Link2 size={14} /> Најтесно Поврзани</h3>
            <div className="space-y-4">
              {relationBands.strongest.map((rel) => (
                <a key={rel.related_entity} href={`/entity/${encodeURIComponent(rel.related_entity)}`} className="entity-related-link">
                  <div>
                    <span className="entity-related-name">{rel.related_entity}</span>
                    <p className="entity-related-band">Тесна врска</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="entity-related-track">
                      <div className="h-full bg-accent" style={{ width: `${Math.min(rel.weight * 10, 100)}%` }} />
                    </div>
                    <span className="entity-related-weight">{rel.weight}</span>
                  </div>
                </a>
              ))}
              {relationBands.strongest.length === 0 && <p className="text-xs text-muted italic">Нема пронајдени силни врски.</p>}
            </div>
          </div>

          <div className="rail-card">
            <h3 className="rail-card-title">Поширок Круг</h3>
            <div className="space-y-4">
              {relationBands.broader.map((rel) => (
                <a key={rel.related_entity} href={`/entity/${encodeURIComponent(rel.related_entity)}`} className="entity-related-link">
                  <div>
                    <span className="entity-related-name">{rel.related_entity}</span>
                    <p className="entity-related-band">Ист контекст</p>
                  </div>
                  <span className="entity-related-weight">{rel.weight}</span>
                </a>
              ))}
              {relationBands.broader.length === 0 && <p className="text-xs text-muted italic">Нема дополнителни врски надвор од најтесниот круг.</p>}
            </div>
          </div>

          <div className="rail-card">
            <h3 className="rail-card-title">Слика Во Бројки</h3>
            <div className="entity-stat-stack">
              <div className="entity-stat-row">
                <span>Кластери на страницата</span>
                <strong>{initialClusters.length}</strong>
              </div>
              <div className="entity-stat-row">
                <span>Активни извори</span>
                <strong>{sources.length}</strong>
              </div>
              <div className="entity-stat-row">
                <span>Кластери со синтеза</span>
                <strong>{initialClusters.filter((cluster) => cluster.has_synthesis).length}</strong>
              </div>
              <div className="entity-stat-row">
                <span>Breaking кластери</span>
                <strong>{initialClusters.filter((cluster) => cluster.is_breaking).length}</strong>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
