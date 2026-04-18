import React, { useEffect, useState } from 'react';
import { Radio, RefreshCcw } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';
import { cleanAndDecode } from '../utils/textUtils';

interface ArticleLike {
  source?: string;
  title?: string;
  created_at?: string;
}

interface ClusterLike {
  cluster_id: string;
  articles?: ArticleLike[];
  is_breaking?: boolean;
}

interface HomeLiveUpdatesIslandProps {
  excludeClusterIds?: string[];
}

interface LiveState {
  count: number;
  time: string;
}

const API_URL = apiBaseUrl();

function getTimeStr(dateStr?: string) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function HomeLiveUpdatesIsland({ excludeClusterIds = [] }: HomeLiveUpdatesIslandProps) {
  const [clusters, setClusters] = useState<ClusterLike[]>([]);
  const [liveState, setLiveState] = useState<LiveState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    const loadLatest = async () => {
      try {
        const res = await fetch(`${API_URL}/news?page_size=12&sort=recent&t=${Date.now()}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        const exclude = new Set(excludeClusterIds);
        const sourceCount: Record<string, number> = {};
        
        const latest = (Array.isArray(data?.clusters) ? data.clusters : [])
          .filter((cluster: ClusterLike) => {
            if (exclude.has(cluster.cluster_id)) return false;
            const src = cluster.articles?.[0]?.source || 'unknown';
            sourceCount[src] = (sourceCount[src] || 0) + 1;
            // Limit to 2 per source in the live view to ensure diversity
            return sourceCount[src] <= 2;
          })
          .slice(0, 4);
        setClusters(latest);
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
            <Radio size={13} /> Во живо
          </p>
          <h2 id="live-now-title">Што пристигнува токму сега</h2>
        </div>
        <div className="live-now-status">
          {liveState ? (
            <>
              <span className="live-now-badge">+{liveState.count} нови објави</span>
              <span className="live-now-time">{getTimeStr(liveState.time)}</span>
            </>
          ) : (
            <span className="live-now-time">Следење во реално време</span>
          )}
        </div>
      </div>

      <div className="live-now-grid">
        {clusters.map((cluster) => {
          const article = cluster.articles?.[0] || {};
          return (
            <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="live-now-card">
              <div className="live-now-meta flex items-center gap-2">
                <span className="live-now-source">{article.source || 'Извор'}</span>
              </div>
              <h3>{cleanAndDecode(article.title || '')}</h3>
              <div className="live-now-footer">
                <span>{getTimeStr(article.created_at)}</span>
                <span className="live-now-open">
                  Отвори <RefreshCcw size={11} />
                </span>
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
