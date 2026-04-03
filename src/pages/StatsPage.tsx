import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { FullStats } from '../types';
import { useUIStore } from '../store/useNewsStore';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from 'recharts';
import { BarChart3, TrendingUp, Database, Zap, Trophy, Cog, Clock, Rss } from 'lucide-react';

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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">⏳ Вчитување статистика...</p>
          <div className="w-12 h-12 border-4 border-primary-300 dark:border-primary-700 border-t-primary-600 dark:border-t-primary-400 rounded-full animate-spin mx-auto" />
        </div>
      </div>
    );
  }

  const sourceChartData = stats.by_source.slice(0, 8).map(s => ({ name: s.source, count: s.n }));
  const categoryChartData = stats.by_category.map(c => ({ name: c.category, count: c.n }));
  const velocityChartData = stats.velocity.slice(0, 24).map(v => ({
    time: new Date(v.t).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' }),
    count: v.n,
  }));

  const COLORS = ['#0284d5', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#ea580c', '#6366f1'];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="text-primary-600 dark:text-primary-400" size={32} />
            <h1 className="text-3xl font-bold text-primary-600 dark:text-primary-400">Статистика</h1>
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Последно ажурирано: {new Date(stats.new_article).toLocaleString('mk-MK')}
          </p>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Key metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="flex items-center gap-3 mb-2">
              <BarChart3 className="text-primary-600 dark:text-primary-400" size={20} />
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold">Вкупно статии</p>
            </div>
            <p className="text-3xl font-bold text-primary-600 dark:text-primary-400">{stats.total_articles.toLocaleString()}</p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-2">Во базата на податоци</p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="flex items-center gap-3 mb-2">
              <Zap className="text-secondary-600 dark:text-secondary-400" size={20} />
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold">Последних 24ч</p>
            </div>
            <p className="text-3xl font-bold text-secondary-600 dark:text-secondary-400">{stats.last_24h}</p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-2">Нови статии</p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="flex items-center gap-3 mb-2">
              <TrendingUp className="text-accent-600 dark:text-accent-400" size={20} />
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold">Синтезирани</p>
            </div>
            <p className="text-3xl font-bold text-accent-600 dark:text-accent-400">{stats.summarized_pct.toFixed(1)}%</p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-2">Со ЈИ синтеза</p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="flex items-center gap-3 mb-2">
              <Database className="text-purple-600 dark:text-purple-400" size={20} />
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold">БД волумен</p>
            </div>
            <p className="text-3xl font-bold text-purple-600 dark:text-purple-400">{stats.db_size_mb.toFixed(1)} MB</p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-2">Големина на база</p>
          </div>
        </div>

        {/* Charts section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Top sources bar chart */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
              <Trophy size={20} className="text-primary-600 dark:text-primary-400" />
              Топ изводи (24ч)
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sourceChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', color: '#fff' }} />
                  <Bar dataKey="count" fill="#0284d5" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category breakdown pie chart */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">По категорија</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryChartData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={(entry) => `${entry.name}`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="count"
                  >
                    {categoryChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', color: '#fff' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Velocity line chart */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 lg:col-span-2">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
              <Zap size={20} className="text-orange-500" />
              Брзина на прилив (последних 24ч)
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={velocityChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', color: '#fff' }} />
                  <Legend />
                  <Line type="monotone" dataKey="count" stroke="#f59e0b" dot={false} name="Статии/час" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Speed leaderboard */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
            <Trophy size={20} className="text-primary-600 dark:text-primary-400" />
            Брзина на објавување
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.speed_leaderboard.slice(0, 9).map((src, idx) => (
              <div key={idx} className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <div className="flex items-center justify-between">
                  <span className="text-gray-700 dark:text-gray-300 font-semibold">
                    {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx + 1}.`} {src.source}
                  </span>
                  <span className="bg-primary-100 dark:bg-primary-900 text-primary-800 dark:text-primary-200 px-3 py-1 rounded-full text-sm font-bold">
                    {src.first_count}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* System info */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
            <Cog size={20} className="text-gray-600 dark:text-gray-400" />
            Системски информации
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="flex items-center gap-3">
              <Clock className="text-green-600 dark:text-green-400" size={20} />
              <div>
                <p className="text-gray-600 dark:text-gray-400 text-sm">Статус</p>
                <p className="text-lg font-bold text-green-600 dark:text-green-400">✓ {stats.uptime}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Rss className="text-primary-600 dark:text-primary-400" size={20} />
              <div>
                <p className="text-gray-600 dark:text-gray-400 text-sm">RSS канали</p>
                <p className="text-lg font-bold text-gray-900 dark:text-white">{stats.total_feeds}</p>
              </div>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Најстара статија</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">
                {new Date(stats.oldest_article).toLocaleDateString('mk-MK')}
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Синтезирани</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{stats.summarized}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
