import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, BookOpen, BarChart3, Zap, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import { TrendingWord } from '../types';
import { useUIStore, useNewsStore } from '../store/useNewsStore';

export const TrendingSidebar: React.FC = () => {
  const [trending, setTrending] = useState<TrendingWord[]>([]);
  const [entities, setEntities] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { setSearchQuery } = useUIStore();
  const { reset } = useNewsStore();

  useEffect(() => {
    const load = async () => {
      try {
        const [trendData, entData] = await Promise.all([
          apiClient.getTrending(),
          fetch('/api/intelligence/top-entities?limit=10').then(r => r.json())
        ]);
        setTrending(trendData.slice(0, 15));
        setEntities(entData || []);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  const handleWordClick = (word: string) => {
    setSearchQuery(word);
    reset();
    navigate('/');
  };

  return (
    <aside className="space-y-4">
      {/* Entities */}
      {!loading && entities.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Users size={16} className="text-accent" />
            <h3 className="section-heading m-0">Луѓе и Организ.</h3>
          </div>
          <div className="space-y-3">
            {entities.map((ent, idx) => (
              <button 
                key={idx}
                onClick={() => navigate(`/entity/${encodeURIComponent(ent.name)}`)}
                className="w-full flex items-center justify-between group border-none bg-transparent p-0 cursor-pointer"
              >
                <span className="text-xs font-bold text-primary group-hover:text-accent transition-colors truncate pr-2">
                  {ent.name}
                </span>
                <span className="text-[10px] font-black text-muted tabular-nums">
                  {ent.total_mentions}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Trending */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp size={16} className="text-brand-600" />
          <h3 className="section-heading">Во тренд</h3>
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton h-7 w-full" />
            ))}
          </div>
        ) : trending.length === 0 ? (
          <p className="text-sm text-ink-muted dark:text-slate-500">Нема трендови</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {trending.map((item, idx) => {
              const isRising = item.trend?.includes('↗') || item.trend?.includes('📈');
              return (
                <button
                  key={idx}
                  onClick={() => handleWordClick(item.word)}
                  className={`pill text-xs transition ${
                    isRising
                      ? 'bg-brand-50 text-brand-700 hover:bg-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:hover:bg-brand-900/50'
                      : 'pill-inactive text-xs'
                  }`}
                  title={`${item.count} споменувања`}
                >
                  {item.word}
                  {isRising && <span className="ml-0.5 text-brand-500">↑</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Quick links */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={16} className="text-amber-500" />
          <h3 className="section-heading">Брзи врски</h3>
        </div>
        <div className="space-y-1">
          <button
            onClick={() => navigate('/briefing')}
            className="w-full flex items-center gap-3 p-2.5 rounded-lg text-left hover:bg-surface-2 dark:hover:bg-dark-3 transition-colors group"
          >
            <BookOpen size={16} className="text-blue-500 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-ink dark:text-slate-200 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                Дневен преглед
              </p>
              <p className="text-xs text-ink-muted dark:text-slate-500">Сублимат на денот</p>
            </div>
          </button>
          <button
            onClick={() => navigate('/stats')}
            className="w-full flex items-center gap-3 p-2.5 rounded-lg text-left hover:bg-surface-2 dark:hover:bg-dark-3 transition-colors group"
          >
            <BarChart3 size={16} className="text-emerald-500 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-ink dark:text-slate-200 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                Статистика
              </p>
              <p className="text-xs text-ink-muted dark:text-slate-500">Активност на медиуми</p>
            </div>
          </button>
        </div>
      </div>
    </aside>
  );
};
