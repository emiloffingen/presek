import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { FullStats } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts';
import {
  ArrowLeft, BarChart3, Zap, Database, Trophy,
  Rss, Clock, TrendingUp, Loader2,
} from 'lucide-react';
import { Header } from '../components/Header';

const COLORS = ['#e82323', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4', '#f97316', '#6366f1'];

const MetricCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}> = ({ icon, label, value, sub, accent = 'text-brand-600 dark:text-brand-400' }) => (
  <div className="card p-5">
    <div className="flex items-center gap-2 mb-2 text-ink-muted dark:text-slate-400">
      {icon}
      <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
    </div>
    <p className={`text-3xl font-bold ${accent}`}>{value}</p>
    {sub && <p className="text-xs text-ink-faint dark:text-slate-500 mt-1">{sub}</p>}
  </div>
);

export const StatsPage: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<FullStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setStats(await apiClient.getFullStats());
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  if (loading || !stats) {
    return (
      <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
        <Header />
        <div className="page-container py-16 flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-brand-600" />
          <p className="text-ink-muted dark:text-slate-400">Вчитување статистика...</p>
        </div>
      </div>
    );
  }

  const sourceData = stats.by_source.slice(0, 8).map((s) => ({ name: s.source, n: s.n }));
  const categoryData = stats.by_category.map((c) => ({ name: c.category || 'Друго', n: c.n }));
  const velocityData = stats.velocity.slice(-24).map((v) => ({
    t: new Date(v.t).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' }),
    n: v.n,
  }));

  const tooltipStyle = {
    backgroundColor: '#1a1d27',
    border: '1px solid #2a2d3a',
    color: '#e2e8f0',
    borderRadius: 8,
    fontSize: 12,
  };

  return (
    <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
      <Header />

      <div className="page-container py-6">
        {/* Page header */}
        <div className="mb-6">
          <button onClick={() => navigate(-1)} className="btn-ghost text-sm mb-4">
            <ArrowLeft size={16} />
            Назад
          </button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center">
              <BarChart3 size={20} className="text-brand-600 dark:text-brand-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-ink dark:text-white">Статистика</h1>
              <p className="text-xs text-ink-muted dark:text-slate-500">
                Ажурирано: {new Date(stats.new_article).toLocaleString('mk-MK')}
              </p>
            </div>
          </div>
        </div>

        {/* Key metrics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <MetricCard
            icon={<BarChart3 size={16} />}
            label="Вкупно статии"
            value={stats.total_articles.toLocaleString()}
            sub="Во базата на податоци"
            accent="text-brand-600 dark:text-brand-400"
          />
          <MetricCard
            icon={<Zap size={16} />}
            label="Последни 24ч"
            value={stats.last_24h}
            sub="Нови статии"
            accent="text-blue-600 dark:text-blue-400"
          />
          <MetricCard
            icon={<TrendingUp size={16} />}
            label="Синтезирани"
            value={`${stats.summarized_pct.toFixed(1)}%`}
            sub="Со АИ синтеза"
            accent="text-amber-600 dark:text-amber-400"
          />
          <MetricCard
            icon={<Database size={16} />}
            label="БД волумен"
            value={`${stats.db_size_mb.toFixed(1)} MB`}
            sub="Големина на база"
            accent="text-emerald-600 dark:text-emerald-400"
          />
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
          {/* Top sources */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Trophy size={16} className="text-amber-500" />
              <h2 className="font-bold text-base text-ink dark:text-white">Топ извори (24ч)</h2>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sourceData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#6b7185' }} />
                  <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 11, fill: '#6b7185' }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="n" fill="#e82323" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category pie */}
          <div className="card p-5">
            <h2 className="font-bold text-base text-ink dark:text-white mb-4">По категорија</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    dataKey="n"
                    labelLine={false}
                    label={({ name, percent }: { name?: string; percent?: number }) =>
                      (percent ?? 0) > 0.05 ? `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%` : ''
                    }
                  >
                    {categoryData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Velocity line */}
          <div className="card p-5 lg:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <Zap size={16} className="text-amber-500" />
              <h2 className="font-bold text-base text-ink dark:text-white">Брзина на прилив (24ч)</h2>
            </div>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={velocityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#6b7185' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7185' }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="n"
                    stroke="#f59e0b"
                    dot={false}
                    strokeWidth={2}
                    name="Статии/час"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Speed leaderboard */}
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-2 mb-4">
            <Trophy size={16} className="text-amber-500" />
            <h2 className="font-bold text-base text-ink dark:text-white">
              Брзина на објавување (7 дена)
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {stats.speed_leaderboard.slice(0, 9).map((src, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-xl bg-surface-2 dark:bg-dark-2 px-4 py-3"
              >
                <span className="text-sm font-semibold text-ink dark:text-slate-200">
                  {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx + 1}.`}{' '}
                  {src.source}
                </span>
                <span className="badge bg-brand-100 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 font-bold">
                  {src.first_count}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* System info */}
        <div className="card p-5">
          <h2 className="section-heading mb-4">Системски информации</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-emerald-500 shrink-0" />
              <div>
                <p className="text-xs text-ink-muted dark:text-slate-500">Статус</p>
                <p className="font-bold text-sm text-emerald-600 dark:text-emerald-400">✓ {stats.uptime}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Rss size={16} className="text-blue-500 shrink-0" />
              <div>
                <p className="text-xs text-ink-muted dark:text-slate-500">RSS канали</p>
                <p className="font-bold text-sm text-ink dark:text-slate-100">{stats.total_feeds}</p>
              </div>
            </div>
            <div>
              <p className="text-xs text-ink-muted dark:text-slate-500">Најстара статија</p>
              <p className="font-semibold text-sm text-ink dark:text-slate-200">
                {new Date(stats.oldest_article).toLocaleDateString('mk-MK')}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-muted dark:text-slate-500">Синтезирани</p>
              <p className="font-bold text-sm text-ink dark:text-slate-100">{stats.summarized}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
