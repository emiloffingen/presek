import { localePathForLang } from '../lib/localePaths';
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
import { useClientTranslations } from '../i18n/clientTranslations';
import { entity } from '../i18n/namespaces/entity';
import type { ui } from '../i18n/ui';

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

function formatDate(value: string | undefined, lang: keyof typeof ui, t: ReturnType<typeof useClientTranslations>) {
  if (!value) return t('entity.unknown');
  try {
    return new Date(value).toLocaleDateString(lang === 'sr' ? 'sr-RS' : 'mk-MK', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return t('entity.unknown');
  }
}

function formatRelative(value: string | undefined, lang: keyof typeof ui, t: ReturnType<typeof useClientTranslations>) {
  if (!value) return t('entity.recently');
  const now = new Date();
  const date = new Date(value);
  const diff = now.getTime() - date.getTime();
  const days = Math.max(0, Math.floor(diff / 86400000));
  if (days === 0) return t('entity.today');
  if (days === 1) return t('entity.yesterday');
  if (days < 7) return t('entity.days_ago').replace('{n}', String(days));
  return formatDate(value, lang, t);
}

function sentimentLabel(score: number, t: ReturnType<typeof useClientTranslations>) {
  if (score >= 0.2) return t('entity.tone_pos');
  if (score <= -0.2) return t('entity.tone_crit');
  return t('entity.tone_neut');
}

function buildTimeline(history: SentimentPoint[], lang: keyof typeof ui) {
  if (!history || !history.length) return [];
  const max = Math.max(1, ...history.map((item) => item.volume || 0));
  return history.map((item) => {
    const date = new Date(item.day);
    return {
      key: item.day,
      label: date.toLocaleDateString(lang === 'sr' ? 'sr-RS' : 'mk-MK', { day: 'numeric', month: 'short' }),
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

function buildWhyItMatters(
  profile: EntityProfile,
  clusters: NewsCluster[],
  related: Relationship[],
  t: ReturnType<typeof useClientTranslations>,
) {
  const recentCount = clusters.length;
  if (recentCount >= 5) {
    return t('entity.why_strong_focus').replace('{name}', profile.name).replace('{count}', String(recentCount));
  }
  if (related.length >= 5) {
    return t('entity.why_network').replace('{name}', profile.name).replace('{count}', String(related.length));
  }
  return t('entity.why_default').replace('{name}', profile.name);
}

function coMentionedEntities(clusters: NewsCluster[], currentName: string) {
  const counts = new Map<string, number>();
  const current = currentName.toLowerCase();
  for (const cluster of clusters) {
    const ents = cluster.entities || [];
    for (const entityName of ents) {
      const clean = String(entityName || '').trim();
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
  lang = 'sr'
}: {
  name: string;
  initialData?: EntityPayload | null;
  lang?: keyof typeof ui;
}) {
  const [data, setData] = useState<EntityPayload | null>(initialData);
  const [loading, setLoading] = useState(!initialData);
  const t = useClientTranslations(lang, entity);

  useEffect(() => {
    if (initialData) return;
    const API_URL = apiBaseUrl();
    fetch(`${API_URL}/intelligence/entity/${encodeURIComponent(name)}?lang=${lang}`)
      .then((res) => res.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name, initialData, lang]);

  if (loading) {
    return (
      <div className="flex flex-col items-center py-20">
        <Loader2 className="animate-spin text-presek-mark mb-4" size={32} />
        <p className="nyt-section-label text-muted-foreground">{t('entity.preparing')}</p>
      </div>
    );
  }

  if (!data) return null;

  const { profile, related, media, categories, sentiment_history, clusters } = data;
  const timeline = buildTimeline(sentiment_history, lang);
  const trend = getSentimentTrend(sentiment_history);
  const relationBands = splitRelated(related);
  const whyItMatters = buildWhyItMatters(profile, clusters, related, t);
  const contextEntities = coMentionedEntities(clusters, profile.name);
  const leadingCategories = (categories || []).slice(0, 4);

  return (
    <div className="entity-flow">
      <header className="entity-hero">
        <div className="entity-hero-main">
          <div className="entity-badge">
            {profile.type === 'PERSON' ? <User size={32} className="text-presek-mark" /> : <Building2 size={32} className="text-presek-mark" />}
          </div>
          <div className="entity-copy">
            <span className="entity-type">{profile.type === 'ORG' ? t('entity.org') : t('entity.person')}</span>
            <p className="entity-summary-copy">
              {t('entity.summary_copy').replace('{name}', profile.name)}
            </p>
          </div>
        </div>

        <div className="entity-metrics">
          <div className="entity-metric">
            <p>{t('entity.total_mentions')}</p>
            <strong>{profile.total_mentions || clusters.length}</strong>
          </div>
          <div className="entity-metric">
            <p>{t('entity.last_seen')}</p>
            <strong>{formatRelative(profile.last_seen || (clusters[0] as any)?.created_at, lang, t)}</strong>
          </div>
          <div className="entity-metric">
            <p>{t('entity.media_tone')}</p>
            <div className="flex flex-col">
                <strong className={profile.sentiment_score > 0.2 ? 'text-green-600' : profile.sentiment_score < -0.2 ? 'text-nyt-red' : 'text-presek-mark'}>
                {sentimentLabel(profile.sentiment_score, t)}
                </strong>
                {trend !== 'stable' && (
                    <span className={`ui-status ${trend === 'improving' ? 'text-green-600' : 'text-nyt-red'}`}>
                        {trend === 'improving' ? t('entity.trend_pos') : t('entity.trend_crit')}
                    </span>
                )}
            </div>
          </div>
          <div className="entity-metric">
            <p>{t('entity.related_subjects')}</p>
            <strong>{related.length}</strong>
          </div>
        </div>
      </header>

      <div className="entity-grid">
        <div className="sources-main">
          <section className="entity-summary entity-featured">
            <h2 className="entity-section-title flex items-center gap-2 md:gap-[var(--grid-gap)]"><Sparkles size={14} /> {t('entity.media_cross_section')}</h2>
            <p className="entity-summary-copy">{whyItMatters}</p>
            <div className="entity-chip-list">
              <span className="entity-chip">{clusters.length} {t('entity.active_topics')}</span>
              <span className="entity-chip">{media.length} {t('entity.leading_media')}</span>
              {categories && categories.length > 0 && (
                  <span className="entity-chip">{t('entity.focus')}: {categories[0].category}</span>
              )}
            </div>
          </section>

          <details className="entity-analytics-details">
            <summary className="entity-analytics-summary">
              <span className="entity-analytics-title">{t('entity.analytics_panel')}</span>
              <span className="entity-analytics-hint">{t('entity.analytics_hint')}</span>
            </summary>
            <div className="entity-analytics-body">
              <div className="entity-insight-grid">
                <section className="entity-summary">
                  <div className="flex flex-col items-start gap-2 md:flex-row md:items-center md:justify-between mb-3 md:mb-4">
                    <h2 className="entity-section-title flex items-center gap-2 md:gap-[var(--grid-gap)] m-0"><TrendingUp size={14} /> {t('entity.dynamics')}</h2>
                    <span className="ui-kicker">{t('entity.last_14_days')}</span>
                  </div>
                  <div className="entity-pulse h-28 md:h-32 flex items-end gap-1 px-1 md:px-2">
                    {timeline.map((item) => (
                      <div key={item.key} className="flex-1 group relative">
                        <div
                            className={`w-full rounded-t-sm transition-all ${item.sentiment > 0.1 ? 'bg-green-500/40' : item.sentiment < -0.1 ? 'bg-nyt-red/40' : 'bg-presek-mark/40'} group-hover:opacity-100`}
                            style={{ height: `${item.percent}%`, opacity: 0.7 }}
                        />
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-foreground text-background text-[9px] font-bold py-1 px-2 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none transition-opacity z-10">
                            {item.count} {t('entity.publications')} • {item.label}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-between mt-2 px-1 ui-kicker text-[8px] md:text-[9px]">
                      <span>{timeline[0]?.label}</span>
                      <span>{timeline[Math.floor(timeline.length/2)]?.label}</span>
                      <span>{timeline[timeline.length-1]?.label}</span>
                  </div>
                </section>

                <section className="entity-summary">
                  <h2 className="entity-section-title flex items-center gap-2 md:gap-[var(--grid-gap)]"><Newspaper size={14} /> {t('entity.thematic_profile')}</h2>
                  <div className="space-y-3 mt-4">
                    {leadingCategories.map((c) => (
                      <div key={c.category} className="flex items-center justify-between">
                        <span className="ui-kicker">{c.category}</span>
                        <div className="flex items-center gap-2 md:gap-[var(--grid-gap)]">
                          <div className="w-20 md:w-24 h-1.5 bg-secondary rounded-full overflow-hidden">
                            <div
                              className="h-full bg-foreground opacity-80"
                              style={{ width: `${Math.min((c.count / (clusters.length || 1)) * 100, 100)}%` }}
                            />
                          </div>
                          <span className="font-sans text-[9px] md:text-[10px] font-black w-7 md:w-8 text-right">{Math.round((c.count / (clusters.length || 1)) * 100)}%</span>
                        </div>
                      </div>
                    ))}
                    {leadingCategories.length === 0 && <p className="text-xs text-muted italic">{t('entity.no_thematic_data')}</p>}
                    {categories && categories.length > leadingCategories.length && (
                      <p className="ui-kicker pt-1">
                        {t('entity.themes_shown').replace('{count}', String(leadingCategories.length))}
                      </p>
                    )}
                  </div>
                </section>
              </div>
            </div>
          </details>

          <section className="entity-summary">
            <h2 className="entity-section-title flex items-center gap-2 md:gap-[var(--grid-gap)]"><Link2 size={14} /> {t('entity.same_context')}</h2>
            <p className="entity-summary-copy">
              {t('entity.co_mention_copy').replace('{name}', profile.name)}
            </p>
            <div className="entity-chip-list">
              {contextEntities.map(([entityName, count]) => (
                <a key={entityName} href={localePathForLang(`/subjekt/${encodeURIComponent(entityName)}`, lang)} className="entity-chip entity-chip-link">
                  {entityName} · {count}
                </a>
              ))}
              {contextEntities.length === 0 && (
                <div className="flex flex-wrap gap-[var(--grid-gap)]">
                  {related.map(r => (
                    <a key={r.related_entity} href={localePathForLang(`/subjekt/${encodeURIComponent(r.related_entity)}`, lang)} className="entity-chip entity-chip-link">
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
            <h3 className="rail-card-title flex items-center gap-2 md:gap-[var(--grid-gap)]"><Link2 size={14} /> {t('entity.closest_connected')}</h3>
            <p className="rail-copy">
              {t('entity.related_rail_copy').replace('{name}', profile.name)}
            </p>
            <div className="space-y-4">
              {relationBands.strongest.map((rel) => (
                <a key={rel.related_entity} href={localePathForLang(`/subjekt/${encodeURIComponent(rel.related_entity)}`, lang)} className="entity-related-link">
                  <div>
                    <span className="entity-related-name">{rel.related_entity}</span>
                    <p className="entity-related-band">{t('entity.tight_bond')}</p>
                  </div>
                  <div className="flex items-center gap-2 md:gap-[var(--grid-gap)]">
                    <div className="entity-related-track">
                      <div className="h-full bg-presek-mark" style={{ width: `${Math.min(rel.weight * 10, 100)}%` }} />
                    </div>
                    <span className="entity-related-weight">{rel.weight}</span>
                  </div>
                </a>
              ))}
              {relationBands.strongest.length === 0 && <p className="text-xs text-muted italic">{t('entity.no_strong_connections')}</p>}
            </div>
          </div>

          <div className="rail-card rail-card-accent">
            <h3 className="rail-card-title">{t('entity.how_to_read')}</h3>
            <p className="rail-copy">
              {t('entity.how_to_read_body').replace('{name}', profile.name)}
            </p>
          </div>

          <div className="rail-card">
            <h3 className="rail-card-title ui-kicker">{t('entity.further')}</h3>
            <div className="flex flex-col gap-2 md:gap-[var(--grid-gap)]">
              <a href={localePathForLang('/archive', lang)} className="entity-related-jump">{t('entity.open_archive')}</a>
              <a href={localePathForLang('/izvori', lang)} className="entity-related-jump">{t('entity.open_sources')}</a>
              <a href={localePathForLang('/pulse', lang)} className="entity-related-jump">{t('entity.compare_media')}</a>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
