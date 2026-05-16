import React, { useEffect, useState } from 'react';
import { Radio, RefreshCcw } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';
import { getDisplayTitle } from '../utils/textUtils';

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
}

interface LiveState {
  count: number;
  time: string;
}

const API_URL = apiBaseUrl();

function getTimeStr(dateStr?: string) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr.replace("Z", ""));
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 1) return 'JUST NOW';
    if (diffMins < 60) return `PRE ${diffMins} MIN`;
    
    return date.toLocaleTimeString('sr-RS', { 
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'Europe/Belgrade' 
    });
  } catch {
    return '';
  }
}

export default function HomeLiveUpdatesIsland({ excludeClusterIds = [], initialClusters = [] }: HomeLiveUpdatesIslandProps) {
  const [clusters, setClusters] = useState<ClusterLike[]>(initialClusters);
  const [liveState, setLiveState] = useState<LiveState | null>(null);
  const [loading, setLoading] = useState(initialClusters.length === 0);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    const loadLatest = async () => {
      try {
        const exclude = encodeURIComponent(excludeClusterIds.join(','));
        const res = await fetch(`${API_URL}/home/live-now?exclude=${exclude}&lang=sr&t=${Date.now()}`);
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
        // Support both batch and single article events
        if (payload?.type !== 'new_articles' && payload?.type !== 'new_article' && payload?.type !== 'new_articles_batch') return;
        
        if (payload.type === 'new_article') {
             setLiveState(prev => ({
                count: (prev?.count || 0) + 1,
                time: payload.time || new Date().toISOString()
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
  }, [excludeClusterIds]);

  if (!loading && clusters.length === 0) {
    return null;
  }

  return (
    <section className="live-now-module motion-rise motion-delay-2" aria-labelledby="live-now-title">
      <div className="live-now-head">
        <div>
          <p className="live-now-kicker">
            <Radio size={13} /> Vo zivo
          </p>
          <h2 id="live-now-title">Sto pristignuva tokmu sega</h2>
        </div>
        <div className="live-now-status">
          {liveState ? (
            <>
              <span className="live-now-badge">+{liveState.count} novi objavi</span>
              <span className="live-now-time">{getTimeStr(liveState.time)}</span>
            </>
          ) : (
            <span className="live-now-time">Sledenje vo realno vreme</span>
          )}
        </div>
      </div>

      <div className="live-now-grid">
        {clusters.map((cluster) => {
          const article = cluster.articles?.[0] || {};
          const title = getDisplayTitle(article);
          return (
            <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="live-now-card group">
              <div className="live-now-meta flex items-center justify-between gap-2 mb-2">
                <span className="live-now-source text-[10px] font-black uppercase tracking-widest text-nyt-accent group-hover:text-foreground transition-colors">{article.source || 'izvor'}</span>
                <span className="text-[10px] font-bold text-muted-foreground tabular-nums">{getTimeStr(article.ingested_at || article.created_at)}</span>
              </div>
              <h3 className="text-sm font-bold leading-snug group-hover:text-nyt-accent transition-colors line-clamp-3">{title}</h3>
              <div className="mt-3 flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                 <RefreshCcw size={12} className="text-nyt-accent animate-spin-slow" />
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
