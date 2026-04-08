import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../api/client';
import { FullStats } from '../types';
import {
  BarChart3, Zap, Database, Trophy,
  Rss, TrendingUp, Loader2,
} from 'lucide-react';
import { Header } from '../components/Header';

const COLORS = ['#cc1a1a', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4', '#f97316', '#6366f1'];

type Point = { t: string; n: number };
type NamedValue = { name: string; n: number };

function VelocityChart({ data }: { data: Point[] }) {
  if (!data.length) {
    return <p className="text-sm text-muted">Нема доволно податоци за овој период.</p>;
  }

  const width = 800;
  const height = 240;
  const paddingX = 18;
  const paddingTop = 16;
  const paddingBottom = 34;
  const chartHeight = height - paddingTop - paddingBottom;
  const maxValue = Math.max(...data.map((point) => point.n), 1);
  const minValue = Math.min(...data.map((point) => point.n), 0);
  const range = Math.max(maxValue - minValue, 1);

  const points = data.map((point, index) => {
    const x = paddingX + (index * (width - paddingX * 2)) / Math.max(data.length - 1, 1);
    const y = paddingTop + chartHeight - ((point.n - minValue) / range) * chartHeight;
    return { ...point, x, y };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(2)} ${(height - paddingBottom).toFixed(2)} L ${points[0].x.toFixed(2)} ${(height - paddingBottom).toFixed(2)} Z`;

  return (
    <div className="rounded-sm border border-color bg-secondary p-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full" role="img" aria-labelledby="velocity-title velocity-desc">
        <title id="velocity-title">Брзина на прилив во последни 24 часа</title>
        <desc id="velocity-desc">
          {`Линиски графикон со ${data.length} временски точки. Минимум: ${minValue}, максимум: ${maxValue} статии по часовен интервал.`}
        </desc>
        <defs>
          <linearGradient id="velocity-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0.04" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((tick) => {
          const y = paddingTop + (chartHeight * tick) / 3;
          return (
            <line
              key={tick}
              x1={paddingX}
              x2={width - paddingX}
              y1={y}
              y2={y}
              stroke="var(--border-color)"
              strokeDasharray="3 5"
            />
          );
        })}
        <path d={areaPath} fill="url(#velocity-fill)" />
        <path d={linePath} fill="none" stroke="var(--accent-color)" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((point, index) =>
          index === 0 || index === points.length - 1 || index % 6 === 0 ? (
            <text key={point.t} x={point.x} y={height - 10} textAnchor="middle" className="fill-[var(--text-muted)] text-[10px] font-bold">
              {point.t}
            </text>
          ) : null
        )}
      </svg>
    </div>
  );
}

function SourceBars({ data }: { data: NamedValue[] }) {
  const maxValue = Math.max(...data.map((item) => item.n), 1);

  return (
    <div className="space-y-4">
      {data.map((item) => {
        const width = `${Math.max((item.n / maxValue) * 100, 6)}%`;
        return (
          <div key={item.name} className="grid grid-cols-[minmax(0,120px)_1fr_auto] items-center gap-3">
            <span className="truncate text-[10px] font-black uppercase tracking-[0.12em] text-primary">
              {item.name}
            </span>
            <div className="h-3 overflow-hidden rounded-full bg-[color:var(--border-color)]/70">
              <div className="h-full rounded-full bg-accent transition-[width]" style={{ width }} />
            </div>
            <span className="text-[11px] font-black text-primary">{item.n}</span>
          </div>
        );
      })}
    </div>
  );
}

function CategoryDonut({ data }: { data: NamedValue[] }) {
  const total = data.reduce((sum, item) => sum + item.n, 0);
  const radius = 62;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="grid gap-6 md:grid-cols-[220px_1fr] md:items-center">
      <div className="mx-auto w-[220px]">
        <svg viewBox="0 0 180 180" className="h-[220px] w-[220px]" role="img" aria-labelledby="donut-title donut-desc">
          <title id="donut-title">Дистрибуција по категории</title>
          <desc id="donut-desc">
            {data.map(d => `${d.name}: ${d.n} (${total ? Math.round((d.n / total) * 100) : 0}%)`).join(', ')}
          </desc>
          <circle cx="90" cy="90" r={radius} fill="none" stroke="var(--border-color)" strokeWidth="22" />
          {data.map((item, index) => {
            const segment = total ? (item.n / total) * circumference : 0;
            const circle = (
              <circle
                key={item.name}
                cx="90"
                cy="90"
                r={radius}
                fill="none"
                stroke={COLORS[index % COLORS.length]}
                strokeWidth="22"
                strokeDasharray={`${segment} ${circumference - segment}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
                transform="rotate(-90 90 90)"
              />
            );
            offset += segment;
            return circle;
          })}
          <text x="90" y="82" textAnchor="middle" className="fill-[var(--text-muted)] text-[10px] font-black uppercase tracking-[0.2em]">
            Категории
          </text>
          <text x="90" y="104" textAnchor="middle" className="fill-[var(--text-primary)] text-[20px] font-black">
            {total}
          </text>
        </svg>
      </div>
      <div className="space-y-3">
        {data.map((item, index) => (
          <div key={item.name} className="flex items-center justify-between gap-4 border-b border-color pb-2">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
              <span className="text-[11px] font-black uppercase tracking-[0.12em] text-primary">{item.name}</span>
            </div>
            <span className="text-[11px] font-bold text-muted">
              {total ? `${((item.n / total) * 100).toFixed(1)}%` : '0%'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export const StatsPage: React.FC = () => {
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
                    <VelocityChart data={velocityData} />
                </section>

                {/* Top Sources Bar */}
                <section>
                    <h2 className="rail-label mb-6 flex items-center gap-2"><Trophy size={14}/> ТОП ИЗВОРИ (24Ч)</h2>
                    <SourceBars data={sourceData} />
                </section>

                {/* Category Pie */}
                <section>
                    <h2 className="rail-label mb-6">ДИСТРИБУЦИЈА ПО КАТЕГОРИИ</h2>
                    <CategoryDonut data={categoryData} />
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
