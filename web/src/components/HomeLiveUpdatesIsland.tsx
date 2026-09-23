import React, { useEffect, useState } from 'react';
import { Radio, RefreshCcw } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';
import { localePathForLang } from '../lib/localePaths';
import { getDisplayTitle, getPersonalizedText } from '../utils/textUtils';
import { useClientTranslations } from '../i18n/clientTranslations';
import { home } from '../i18n/namespaces/home';
import { common } from '../i18n/namespaces/common';
import { news } from '../i18n/namespaces/news';

interface ArticleLike {
  source?: string;
  title?: string;
  display_title?: string;
  created_at?: string;
  ingested_at?: string;
}

interface ClusterLike {
  cluster_id: string;
  articles?: ArticleLike[];
  is_breaking?: boolean;
}

interface HomeLiveUpdatesIslandProps {
  excludeClusterIds?: string[];
  initialClusters?: ClusterLike[];
  lang?: string;
}

interface LiveState {
  count: number;
  time: string;
}

const API_URL = apiBaseUrl();

export default function HomeLiveUpdatesIsland({ excludeClusterIds = [], initialClusters = [], lang = 'mk' }: HomeLiveUpdatesIslandProps) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, home, common, news);
  const [clusters, setClusters] = useState<ClusterLike[]>(initialClusters);
  const [liveState, setLiveState] = useState<LiveState | null>(null);
  const [loading, setLoading] = useState(initialClusters.length === 0);

  const getTimeStr = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr.replace('Z', ''));
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));

      if (diffMins < 1) return t('news.just_now');
      if (diffMins < 60) return `${t('news.ago')} ${diffMins} ${t('news.min_short')}`;

      return date.toLocaleTimeString(locale === 'sr' ? 'sr-RS' : 'mk-MK', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Europe/Belgrade',
      });
    } catch {
      return '';
    }
  };

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    const loadLatest = async () => {
      try {
        const exclude = encodeURIComponent(excludeClusterIds.join(','));
        const res = await fetch(`${API_URL}/home/live-now?exclude=${exclude}&lang=${lang}&t=${Date.now()}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setClusters(Array.isArray(data?.clusters) ? data.clusters : []);
      } catch (err) {
        console.error('[HomeLiveUpdates] Failed to load latest clusters:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    const source = new EventSource('/api/live');
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type !== 'new_articles' && payload?.type !== 'new_article' && payload?.type !== 'new_articles_batch') return;

        if (payload.type === 'new_article') {
          setLiveState(prev => ({
            count: (prev?.count || 0) + 1,
            time: payload.time || new Date().toISOString(),
          }));
        } else {
          setLiveState({
            count: Number(payload.count || 0),
            time: String(payload.time || ''),
          });
        }

        if (refreshTimer) clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => {
          loadLatest();
        }, 250);
      } catch (err) {
        console.error('[HomeLiveUpdates] Failed to parse SSE payload:', err);
      }
    };
    source.onerror = () => {
      source.close();
    };

    loadLatest();

    return () => {
      cancelled = true;
      if (refreshTimer) clearTimeout(refreshTimer);
      source.close();
    };
  }, [excludeClusterIds, lang]);

  if (!loading && clusters.length === 0) {
    return null;
  }

  return (
    <section className="live-now-module motion-rise motion-delay-2" aria-labelledby="live-now-title">
      <div className="live-now-head">
        <div>
          <p className="live-now-kicker">
            <Radio size={13} /> {t('home.live_kicker')}
          </p>
          <h2 id="live-now-title">{t('home.live_title')}</h2>
        </div>
        <div className="live-now-status">
          {liveState ? (
            <>
              <span className="live-now-badge">+{liveState.count} {t('home.live_new_posts')}</span>
              <span className="live-now-time">{getTimeStr(liveState.time)}</span>
            </>
          ) : (
            <span className="live-now-time">{t('home.live_tracking')}</span>
          )}
        </div>
      </div>

      <div className="live-now-grid">
        {clusters.map((cluster) => {
          const article = cluster.articles?.[0] || {};
          const title = getPersonalizedText(getDisplayTitle(article, '', lang), lang);
          return (
            <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, locale)} className="live-now-card group">
              <div className="live-now-meta flex items-center justify-between gap-[var(--grid-gap)] mb-2">
                <span className="live-now-source text-[10px] font-black uppercase tracking-widest text-presek-mark group-hover:text-foreground transition-colors">{article.source || t('for_you.default_source')}</span>
                <span className="text-[10px] font-bold text-muted-foreground tabular-nums">{getTimeStr(article.ingested_at || article.created_at)}</span>
              </div>
              <h3 className="text-sm font-bold leading-snug group-hover:text-presek-mark transition-colors line-clamp-3">{title}</h3>
              <div className="mt-3 flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                 <RefreshCcw size={12} className="text-presek-mark animate-spin-slow" />
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
