import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useNewsStore } from '@/store/useNewsStore';
import * as api from '@/api/client';

export const TrendingSidebar: React.FC = () => {
  const { trending, setTrending } = useNewsStore();

  useEffect(() => {
    const fetchTrending = async () => {
      const data = await api.fetchTrending();
      setTrending(data);
    };
    fetchTrending();
    const interval = setInterval(fetchTrending, 300000); // 5 mins
    return () => clearInterval(interval);
  }, [setTrending]);

  if (trending.length === 0) return null;

  return (
    <div className="trending-widget fade-in">
      <h3 className="widget-title">Во Трендов</h3>
      <div className="trending-list">
        {trending.slice(0, 10).map((t, i) => (
          <Link key={i} to={`/?q=${encodeURIComponent(t.word)}`} className="trending-item">
            <span className="trending-rank">{i + 1}</span>
            <span className="trending-word">{t.word}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};
