import React, { useEffect, useMemo, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { fetchNews, fetchTrending, fetchStatsFull } from './api/client';
import { Cluster, TrendingItem } from '@/types';

export const FrontendV2: React.FC = () => {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [trending, setTrending] = useState<TrendingItem[]>([]);
  const [topic, setTopic] = useState('');
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ total_articles: number; last_24h: number; summarized_pct: number } | null>(null);
  const [liveUpdates, setLiveUpdates] = useState<number>(0);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const [trendingData, statsData] = await Promise.all([
          fetchTrending(),
          fetchStatsFull()
        ]);
        setTrending(trendingData);
        setStats({
          total_articles: statsData.total_articles,
          last_24h: statsData.last_24h,
          summarized_pct: statsData.summarized_pct
        });
      } catch (e) {
        console.error('Failed to load meta data', e);
      }
    };
    loadMeta();
  }, []);

  useEffect(() => {
    const loadNews = async () => {
      setIsLoading(true);
      setError(null);
      try {
        // Use forceRefresh=true and cache busting for fresh content
        const news = await fetchNews(0, topic, submittedQuery, true);
        setClusters(news.data);
        setLastUpdated(new Date().toISOString());
      } catch (e) {
        setError('Не успеавме да вчитаме вести. Обидете се повторно.');
      } finally {
        setIsLoading(false);
      }
    };

    loadNews();
  }, [topic, submittedQuery]);

  // Set up Server-Sent Events for live updates
  useEffect(() => {
    const setupSSE = () => {
      if (sseRef.current) {
        sseRef.current.close();
      }

      sseRef.current = new EventSource('/api/live');

      sseRef.current.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type === 'new_article' || payload?.type === 'new_articles' || payload?.type === 'new_articles_batch') {
            setLiveUpdates(prev => prev + (payload.count || 1));
            setLastUpdated(payload.time || new Date().toISOString());
          }
        } catch (err) {
          console.error('Failed to parse SSE payload:', err);
        }
      };

      sseRef.current.onerror = () => {
        sseRef.current?.close();
        // Try to reconnect after 5 seconds
        setTimeout(setupSSE, 5000);
      };

      return () => {
        sseRef.current?.close();
      };
    };

    const cleanup = setupSSE();
    return cleanup;
  }, []);

  const topCluster = clusters[0];
  const secondaryClusters = useMemo(() => clusters.slice(1, 7), [clusters]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittedQuery(query.trim());
  };

  return (
    <div className="v2-shell fade-in">
      <header className="v2-hero">
        <div>
          <p className="rail-label">PRESEK NEXT</p>
          <h1>нова фронтенд контролна табла за вашиот бекенд</h1>
          <p className="v2-subtitle">Брз преглед на кластери, трендови и метрики од API-то.</p>
        </div>

        <form className="v2-search" onSubmit={onSearch}>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Пребарај тема или збор..."
            aria-label="Пребарај"
          />
          <button type="submit" className="cat-btn">Пребарај</button>
        </form>

        <div className="v2-topics">
          {['', 'Политика', 'Спорт', 'Технологија', 'Економија'].map((item) => (
            <button
              key={item || 'all'}
              className={`cat-btn ${topic === item ? 'active' : ''}`}
              onClick={() => setTopic(item)}
            >
              {item || 'Сите'}
            </button>
          ))}
        </div>
        {liveUpdates > 0 && (
          <div className="live-updates-badge">
            🔴 {liveUpdates} нови вести - последно ажурирано: {new Date(lastUpdated).toLocaleTimeString('mk-MK')}
          </div>
        )}
      </header>

      {stats && (
        <section className="v2-stats">
          <div className="glass-card"><strong>{stats.total_articles.toLocaleString()}</strong><span>вкупно статии</span></div>
          <div className="glass-card"><strong>{stats.last_24h.toLocaleString()}</strong><span>последни 24 часа</span></div>
          <div className="glass-card"><strong>{Math.round(stats.summarized_pct)}%</strong><span>со AI резиме</span></div>
        </section>
      )}

      {error && <div className="error-state">{error}</div>}

      {isLoading ? (
        <div className="v2-grid"><div className="skeleton-box" style={{ height: 280 }} /></div>
      ) : (
        <section className="v2-grid">
          {topCluster && (
            <article className="v2-lead">
              {topCluster.representative_image && (
                <img src={topCluster.representative_image} alt={topCluster.articles[0]?.title || 'lead'} />
              )}
              <div>
                <p className="src-badge">ВОДЕЧКА приказна</p>
                <h2>{topCluster.articles[0]?.title}</h2>
                <p>{topCluster.articles[0]?.description || 'Нема опис за оваа статија.'}</p>
                <Link to={`/cluster/${topCluster.cluster_id}`} className="cat-btn">Отвори кластер</Link>
              </div>
            </article>
          )}

          <div className="v2-cards">
            {secondaryClusters.map((cluster) => (
              <Link key={cluster.cluster_id} to={`/cluster/${cluster.cluster_id}`} className="v2-card">
                <h3>{cluster.articles[0]?.title}</h3>
                <p>{cluster.articles[0]?.source} • {cluster.articles.length} извори</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <aside className="v2-trending">
        <div className="trending-header">
          <h3>Тренд теми</h3>
          <button 
            className="refresh-btn"
            onClick={() => {
              // Force refresh trending data
              fetchTrending().then(newTrending => {
                setTrending(newTrending);
                setLastUpdated(new Date().toISOString());
              }).catch(console.error);
            }}
            title="Освежи трендови"
          >
            🔄 Освежи
          </button>
        </div>
        <div className="ribbon-scroll">
          {trending.slice(0, 12).map((item) => (
            <button key={item.word} className="ribbon-item" onClick={() => { setQuery(item.word); setSubmittedQuery(item.word); }}>
              #{item.word}
            </button>
          ))}
        </div>
      </aside>
    </div>
    
    {/* Inline styles for live update elements */}
    <style jsx="true">{
      `
      .live-updates-badge {
        background: rgba(255, 0, 0, 0.1);
        border: 1px solid rgba(255, 0, 0, 0.3);
        color: #ff0000;
        padding: 8px 12px;
        border-radius: 8px;
        margin: 10px 0;
        font-size: 14px;
        font-weight: bold;
        text-align: center;
        animation: pulse 2s infinite;
      }
      
      .trending-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
      }
      
      .refresh-btn {
        background: rgba(30, 144, 255, 0.1);
        border: 1px solid rgba(30, 144, 255, 0.3);
        color: #1e90ff;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
      }
      
      .refresh-btn:hover {
        background: rgba(30, 144, 255, 0.2);
      }
      
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
      }
      `
    }
    </style>
  );
};
