import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { FullStats } from '../types';
import { useUIStore } from '../store/useNewsStore';

export const StatsPage: React.FC = () => {
  const [stats, setStats] = useState<FullStats | null>(null);
  const [loading, setLoading] = useState(true);
  const { setStats: setStoreStats } = useUIStore();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getFullStats();
        setStats(data);
        setStoreStats(data);
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, [setStoreStats]);

  if (loading || !stats) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 text-lg mb-4">⏳ Вчитување статистика...</p>
          <div className="w-12 h-12 border-4 border-blue-300 border-t-blue-600 rounded-full animate-spin mx-auto" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h1 className="text-3xl font-bold text-blue-600">📊 Статистика</h1>
          <p className="text-gray-600">
            Последно ажурирано: {new Date(stats.new_article).toLocaleString('mk-MK')}
          </p>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Key metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow-md p-6">
            <p className="text-gray-600 text-sm font-semibold mb-2">Вкупно статии</p>
            <p className="text-3xl font-bold text-blue-600">{stats.total_articles.toLocaleString()}</p>
            <p className="text-gray-500 text-xs mt-2">Во базата на податоци</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <p className="text-gray-600 text-sm font-semibold mb-2">Последних 24ч</p>
            <p className="text-3xl font-bold text-green-600">{stats.last_24h}</p>
            <p className="text-gray-500 text-xs mt-2">Нови статии</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <p className="text-gray-600 text-sm font-semibold mb-2">Синтезирани</p>
            <p className="text-3xl font-bold text-yellow-600">{stats.summarized_pct.toFixed(1)}%</p>
            <p className="text-gray-500 text-xs mt-2">Со ЈИ синтеза</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <p className="text-gray-600 text-sm font-semibold mb-2">БД волумен</p>
            <p className="text-3xl font-bold text-purple-600">{stats.db_size_mb.toFixed(1)} MB</p>
            <p className="text-gray-500 text-xs mt-2">Големина на база</p>
          </div>
        </div>

        {/* Charts section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Top sources */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4">🏆 Топ изводи (24ч)</h2>
            <div className="space-y-3">
              {stats.by_source.slice(0, 10).map((source, idx) => (
                <div key={idx} className="flex justify-between items-center">
                  <span className="text-gray-700">
                    {idx + 1}. {source.source}
                  </span>
                  <div className="w-48 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600 transition-all"
                      style={{
                        width: `${(source.n / (stats.by_source[0]?.n || 1)) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="text-gray-600 font-semibold ml-2">{source.n}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category breakdown */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4">📍 По категорија</h2>
            <div className="space-y-3">
              {stats.by_category.map((cat, idx) => (
                <div key={idx} className="flex justify-between items-center">
                  <span className="text-gray-700">{cat.category}</span>
                  <div className="w-48 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-600 transition-all"
                      style={{
                        width: `${(cat.n / (stats.by_category[0]?.n || 1)) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="text-gray-600 font-semibold ml-2">{cat.n}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Velocity */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4">⚡ Брзина на прилив (последних 24ч)</h2>
            <div className="space-y-2">
              {stats.velocity.slice(0, 10).map((v, idx) => (
                <div key={idx} className="flex justify-between items-center text-sm">
                  <span className="text-gray-600">
                    {new Date(v.t).toLocaleTimeString('mk-MK', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500 transition-all"
                        style={{
                          width: `${(v.n / (stats.velocity[0]?.n || 1)) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="font-semibold text-gray-700 w-8 text-right">{v.n}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Speed leaderboard */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4">🚀 Брзина на објавување</h2>
            <div className="space-y-3">
              {stats.speed_leaderboard.slice(0, 10).map((src, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-gray-700">
                    {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx + 1}.`} {src.source}
                  </span>
                  <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-bold">
                    {src.first_count} прва
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* System info */}
        <div className="bg-white rounded-lg shadow-md p-6 mt-6">
          <h2 className="text-xl font-bold mb-4">🔧 Системски информации</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-gray-600 text-sm">Статус</p>
              <p className="text-lg font-bold text-green-600">✓ {stats.uptime}</p>
            </div>
            <div>
              <p className="text-gray-600 text-sm">RSS канали</p>
              <p className="text-lg font-bold">{stats.total_feeds}</p>
            </div>
            <div>
              <p className="text-gray-600 text-sm">Најстара статија</p>
              <p className="text-sm font-semibold">
                {new Date(stats.oldest_article).toLocaleDateString('mk-MK')}
              </p>
            </div>
            <div>
              <p className="text-gray-600 text-sm">Задува сита синтеза</p>
              <p className="text-lg font-bold">{stats.summarized}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
