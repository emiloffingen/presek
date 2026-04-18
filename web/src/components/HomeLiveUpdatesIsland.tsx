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
        const res = await fetch(`${API_URL}/news?page_size=12`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        const exclude = new Set(excludeClusterIds);
        const latest = (Array.isArray(data?.clusters) ? data.clusters : [])
          .filter((cluster: ClusterLike) => !exclude.has(cluster.cluster_id))
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
        if (payload?.type !== 'new_articles') return;
        setLiveState({
          count: Number(payload.count || 0),
          time: String(payload.time || ''),
        });
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
              <div className="live-now-meta">
                <span className="live-now-source">{article.source || 'Извор'}</span>
                {cluster.is_breaking && <span className="live-now-flash">Во живо</span>}
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
