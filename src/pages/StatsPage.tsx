import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { FullStats } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts';
import {
  BarChart3, Zap, Database, Trophy,
  Rss, Clock, TrendingUp, Loader2,
} from 'lucide-react';
import { Header } from '../components/Header';

const COLORS = ['#cc1a1a', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4', '#f97316', '#6366f1'];

export const StatsPage: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<FullStats | null>(() => window.__INITIAL_STATS_DATA__);
  const [loading, setLoading] = useState(!stats);
  const hydrated = useRef(!!stats);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await apiClient.getFullStats();
        setStats(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
        hydrated.current = true;
      }
    };
    
    if (!hydrated.current) {
        load();
    }
    
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  if (loading && !stats) {
    return (
      <div className="min-h-screen bg-primary">
        <Header />
        <div className="page-container py-16 flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-accent" />
          <p className="text-muted">Вчитување статистика...</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const sourceData = stats.by_source.slice(0, 10).map((s) => ({ name: s.source, n: s.n }));
  const categoryData = stats.by_category.map((c) => ({ name: c.category || 'Друго', n: c.n }));
  const velocityData = stats.velocity.slice(-24).map((v) => ({
    t: new Date(v.t).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' }),
    n: v.n,
  }));

  const isDark = document.documentElement.classList.contains('dark');
  const tooltipStyle = {
    backgroundColor: isDark ? '#1a1d27' : '#ffffff',
    border: `1px solid ${isDark ? '#2a2d3a' : '#e4e4e8'}`,
    color: isDark ? '#f1f5f9' : '#0f1117',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 'bold'
  };

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        <header className="mb-10 border-b-2 border-primary pb-8">
            <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5 mb-4 inline-block">АНАЛИТИКА</span>
            <h1 className="font-serif text-3xl md:text-5xl font-bold leading-tight text-primary mb-4">
                Медиумски Пулс
            </h1>
            <p className="text-xs text-muted font-bold uppercase tracking-tighter">
                Ажурирано: {new Date(stats.new_article).toLocaleString('mk-MK')}
            </p>
        </header>

        {/* Unified metrics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
            <div className="border-t-2 border-primary pt-4">
                <p className="text-[10px] font-black text-muted uppercase mb-1 flex items-center gap-1"><BarChart3 size={10}/> Вкупно статии</p>
                <p className="text-3xl font-serif font-bold text-primary">{stats.total_articles.toLocaleString()}</p>
            </div>
            <div className="border-t-2 border-primary pt-4">
                <p className="text-[10px] font-black text-muted uppercase mb-1 flex items-center gap-1"><Zap size={10}/> Последни 24ч</p>
                <p className="text-3xl font-serif font-bold text-accent">{stats.last_24h}</p>
            </div>
            <div className="border-t-2 border-primary pt-4">
                <p className="text-[10px] font-black text-muted uppercase mb-1 flex items-center gap-1"><TrendingUp size={10}/> Пресек Сублимат</p>
                <p className="text-3xl font-serif font-bold text-primary">{stats.summarized_pct.toFixed(1)}%</p>
            </div>
            <div className="border-t-2 border-primary pt-4">
                <p className="text-[10px] font-black text-muted uppercase mb-1 flex items-center gap-1"><Rss size={10}/> Извори</p>
                <p className="text-3xl font-serif font-bold text-primary">{stats.total_feeds}</p>
            </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <div className="lg:col-span-8 space-y-12">
                {/* Velocity Line */}
                <section>
                    <h2 className="rail-label mb-6 flex items-center gap-2"><Zap size={14}/> БРЗИНА НА ПРИЛИВ (24Ч)</h2>
                    <div className="h-64 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={velocityData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                                <XAxis dataKey="t" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                                <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Line type="monotone" dataKey="n" stroke="var(--accent-color)" dot={false} strokeWidth={3} name="Статии" />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </section>

                {/* Top Sources Bar */}
                <section>
                    <h2 className="rail-label mb-6 flex items-center gap-2"><Trophy size={14}/> ТОП ИЗВОРИ (24Ч)</h2>
                    <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={sourceData} layout="vertical">
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
                                <XAxis type="number" hide />
                                <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10, fontWeight: 'bold', fill: 'var(--text-primary)' }} axisLine={false} tickLine={false} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Bar dataKey="n" fill="var(--accent-color)" radius={[0, 2, 2, 0]} barSize={20} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </section>

                {/* Category Pie */}
                <section>
                    <h2 className="rail-label mb-6">ДИСТРИБУЦИЈА ПО КАТЕГОРИИ</h2>
                    <div className="h-64 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={categoryData}
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="n"
                                >
                                    {categoryData.map((_, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend verticalAlign="middle" align="right" layout="vertical" iconType="circle" wrapperStyle={{ fontSize: 10, fontWeight: 'bold', textTransform: 'uppercase' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </section>
            </div>

            <aside className="lg:col-span-4 space-y-10">
                <div className="rail-widget border-t-2 border-primary">
                    <h3 className="rail-label flex items-center gap-2"><Database size={14}/> СИСТЕМСКИ ПОДАТОЦИ</h3>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center py-2 border-b border-color">
                            <span className="text-[10px] font-bold text-muted uppercase">Статус</span>
                            <span className="text-[10px] font-black text-emerald-500 uppercase">✓ {stats.uptime}</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-color">
                            <span className="text-[10px] font-bold text-muted uppercase">Волумен</span>
                            <span className="text-[10px] font-black text-primary uppercase">{stats.db_size_mb.toFixed(1)} MB</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-color">
                            <span className="text-[10px] font-bold text-muted uppercase">Најстара статија</span>
                            <span className="text-[10px] font-black text-primary uppercase">{new Date(stats.oldest_article).toLocaleDateString('mk-MK')}</span>
                        </div>
                    </div>
                </div>

                <div className="rail-widget border-t-2 border-primary">
                    <h3 className="rail-label flex items-center gap-2"><Trophy size={14}/> ЛИДЕРБОРД (7 ДЕНА)</h3>
                    <p className="text-[10px] text-muted mb-4 uppercase font-bold">Медиуми кои први ги објавуваат вестите</p>
                    <div className="space-y-3">
                        {stats.speed_leaderboard.slice(0, 8).map((src, idx) => (
                            <div key={src.source} className="flex justify-between items-center">
                                <span className="text-[11px] font-bold text-primary uppercase">{idx + 1}. {src.source}</span>
                                <span className="text-[10px] font-black text-accent">{src.first_count}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </aside>
        </div>
      </div>
    </div>
  );
};
