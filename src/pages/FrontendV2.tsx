import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchNews, fetchTrending, fetchStatsFull } from '@/api/client';
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
        const news = await fetchNews(0, topic, submittedQuery, false);
        setClusters(news.data);
      } catch (e) {
        setError('Не успеавме да вчитаме вести. Обиди се повторно.');
      } finally {
        setIsLoading(false);
      }
    };

    loadNews();
  }, [topic, submittedQuery]);

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
          <h1>Нова фронтенд контролна табла за твојот backend</h1>
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
          {['', 'Politics', 'Sport', 'Tech', 'Economy'].map((item) => (
            <button
              key={item || 'all'}
              className={`cat-btn ${topic === item ? 'active' : ''}`}
              onClick={() => setTopic(item)}
            >
              {item || 'Сите'}
            </button>
          ))}
        </div>
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
                <p className="src-badge">ВОДЕЧКА ПРИКАЗНА</p>
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
        <h3>Trending</h3>
        <div className="ribbon-scroll">
          {trending.slice(0, 12).map((item) => (
            <button key={item.word} className="ribbon-item" onClick={() => { setQuery(item.word); setSubmittedQuery(item.word); }}>
              #{item.word}
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
};
