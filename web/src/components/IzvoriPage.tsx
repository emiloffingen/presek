import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, ShieldCheck, Zap, Activity, LineChart, ShieldAlert, Info } from 'lucide-react';

interface SourceRow {
  source: string;
  country: string;
  category: string;
  top_categories: string[];
  credibility: number;
  effective_weight: number;
  trust_tier: string;
  recent_volume: number;
  speed_first_count: number;
  lead_count_30d: number;
  corroborated_lead_count_30d: number;
  solo_lead_count_30d: number;
  corroboration_rate: number;
  lone_lead_rate: number;
  recent_7d_volume: number;
  previous_7d_volume: number;
  trend_delta: number;
  trend_label: string;
  quality_score: number | null;
  tendency: string;
  is_active: boolean;
  last_fetched?: string;
  pause_mode?: string | null;
  pause_reason?: string | null;
}

function tierClass(tier: string) {
  if (tier === 'Висока доверба') return 'source-tier-high';
  if (tier === 'Потврден извор') return 'source-tier-medium';
  return 'source-tier-low';
}

function formatLastFetched(value?: string) {
  if (!value) return 'Нема свеж сигнал';
  try {
    const date = new Date(value);
    return date.toLocaleString('mk-MK', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return 'Нема свеж сигнал';
  }
}

function formatPercent(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function trendClass(label?: string) {
  if (label === 'Расте') return 'source-trend-up';
  if (label === 'Слабее') return 'source-trend-down';
  return 'source-trend-flat';
}

function getHealthStatus(lastFetched?: string): 'active' | 'stale' | 'critical' {
  if (!lastFetched) return 'critical';
  try {
    const diffMs = Date.now() - new Date(lastFetched).getTime();
    const diffMins = diffMs / (1000 * 60);
    if (diffMins <= 60) return 'active';
    if (diffMins <= 360) return 'stale';
    return 'critical';
  } catch {
    return 'critical';
  }
}

export const IzvoriPage: React.FC = () => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTier, setFilterTier] = useState<string>('all');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${apiBaseUrl()}/sources?_t=${Date.now()}`);
        if (!res.ok) {
          setError('Неуспешно поврзување со серверот.');
          return;
        }
        const allRes = await res.json();
        if (!Array.isArray(allRes)) {
          setError('Грешка при вчитување на податоците.');
          return;
        }
        setSources(allRes);
      } catch {
        setError('Неуспешно поврзување со серверот.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filtered = useMemo(() => {
    let results = sources;
    
    const q = searchTerm.trim().toLowerCase();
    if (q) {
      results = results.filter((source) => source.source?.toLowerCase().includes(q));
    }
    
    if (filterTier === 'high') {
      results = results.filter(s => s.trust_tier === 'Висока доверба');
    } else if (filterTier === 'verified') {
      results = results.filter(s => s.trust_tier === 'Потврден извор');
    }
    
    return results;
  }, [sources, searchTerm, filterTier]);

  const mkSources = filtered.filter((s) => s.country === 'MK' || !s.country);
  const intSources = filtered.filter((s) => s.country && s.country !== 'MK');
  const highTrust = filtered.filter((s) => s.trust_tier === 'Висока доверба').length;
  const fastMovers = [...filtered].sort((a, b) => b.speed_first_count - a.speed_first_count).slice(0, 5);
  const bestCorroborated = [...filtered]
    .filter((s) => s.lead_count_30d >= 3)
    .sort((a, b) => b.corroboration_rate - a.corroboration_rate)
    .slice(0, 5);
  const loneLeaders = [...filtered]
    .filter((s) => s.lead_count_30d >= 3)
    .sort((a, b) => b.lone_lead_rate - a.lone_lead_rate)
    .slice(0, 5);

  const renderSourceCard = (source: SourceRow) => {
    const health = getHealthStatus(source.last_fetched);
    const reliabilityIndex = ((source.corroboration_rate * 0.7) + ((source.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);
    
    return (
      <a key={source.source} href={`/?q=${encodeURIComponent(source.source)}`} className="source-reputation-card group">
        <div className="source-reputation-top">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full ${
                health === 'active' ? 'bg-green-500 animate-pulse shadow-[0_0_5px_rgba(34,197,94,0.5)]' : 
                health === 'stale' ? 'bg-amber-400' : 'bg-red-500'
              }`} title={
                health === 'active' ? 'Активен (ажуриран неодамна)' : 
                health === 'stale' ? 'Во мирување (нема сигнал >1ч)' : 'Неактивен (нема сигнал >6ч)'
              }></div>
              <h3 className="source-reputation-name group-hover:text-nyt-accent transition-colors">{source.source}</h3>
            </div>
            <div className="flex flex-wrap gap-1 mt-1.5">
                <span className="source-reputation-meta px-1.5 py-0.5 bg-secondary rounded text-[9px] font-black uppercase tracking-tighter">{source.country || 'MK'}</span>
                {source.top_categories?.slice(0, 2).map(cat => (
                    <span key={cat} className="source-reputation-meta px-1.5 py-0.5 border border-border rounded text-[9px] font-black uppercase tracking-tighter opacity-70 bg-background">{cat}</span>
                ))}
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            <span className={`source-tier ${tierClass(source.trust_tier)} text-[10px]`}>{source.trust_tier}</span>
            <div className="flex items-center gap-1.5">
                <span className="text-[9px] font-black uppercase opacity-40">QI:</span>
                <span className="text-[11px] font-black text-nyt-accent">{reliabilityIndex}</span>
            </div>
          </div>
        </div>

        <p className="source-reputation-copy line-clamp-2">{source.tendency}</p>
        
        {/* Reliability Mini-Chart */}
        <div className="mt-4 mb-2">
            <div className="flex justify-between items-center text-[9px] font-black uppercase tracking-tighter mb-1.5 opacity-60">
                <div className="flex items-center gap-1">
                  <span>Сигурност на водство</span>
                </div>
                <span>{formatPercent(source.corroboration_rate)}</span>
            </div>
            <div className="flex h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div 
                  className="h-full bg-nyt-accent shadow-[0_0_8px_rgba(var(--nyt-accent-rgb),0.4)]" 
                  title="Води и е потврден"
                  style={{ width: `${(source.corroboration_rate || 0) * 100}%` }} 
                />
                <div 
                  className="h-full bg-orange-400 opacity-50" 
                  title="Води сам"
                  style={{ width: `${(source.lone_lead_rate || 0) * 100}%` }} 
                />
            </div>
        </div>

      <div className="flex items-center justify-between mt-4 pt-4 border-t border-border/50">
        <div className="flex flex-col">
            <span className="text-[9px] font-black uppercase opacity-50">7д Тренд</span>
            <p className={`source-trend-note ${trendClass(source.trend_label)} !m-0 !p-0 border-0 bg-transparent`}>
                <span className="font-black">{source.trend_label}</span>
                <strong className="text-[10px] ml-1">{source.trend_delta >= 0 ? `+${source.trend_delta}` : source.trend_delta}</strong>
            </p>
        </div>

        <div className="flex gap-4">
            <div className="text-right">
                <span className="text-[9px] font-black uppercase opacity-50 block">24ч Обем</span>
                <span className="text-xs font-black">{source.recent_volume}</span>
            </div>
            <div className="text-right">
                <span className="text-[9px] font-black uppercase opacity-50 block">Прв</span>
                <span className="text-xs font-black text-nyt-accent">{source.speed_first_count}</span>
            </div>
        </div>
      </div>

      <div className="source-reputation-footer mt-4">
        <span>{formatLastFetched(source.last_fetched)}</span>
        {!source.is_active && <span className="source-status-paused">Паузиран</span>}
      </div>
    </a>
  );
};

  return (
    <div className="sources-container">
      <div className="py-2 md:py-4">
        <header className="sources-header">
          <span className="sources-kicker">Репутација</span>
          <h1 className="sources-headline">Медиумски Извори</h1>
          <p className="sources-intro">
            Преглед на изворите што Пресек ги следи, со ниво на доверба, дневен ритам, сигнал за брзина и присуство во покривањето.
          </p>
          <div className="max-w-xl mt-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Пребарај извори..."
                className="w-full bg-secondary border border-border pl-10 pr-4 py-2 text-sm text-foreground focus:outline-none focus:border-nyt-accent transition-colors rounded-full"
              />
            </div>
            
            {/* Quick Filters */}
            <div className="flex flex-wrap gap-2 mt-4">
               {[
                 { id: 'all', label: 'Сите' },
                 { id: 'high', label: 'Висока доверба' },
                 { id: 'verified', label: 'Потврдени' }
               ].map(btn => (
                 <button
                   key={btn.id}
                   onClick={() => setFilterTier(btn.id)}
                   className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border ${
                     filterTier === btn.id 
                       ? 'bg-nyt-accent text-white border-nyt-accent shadow-sm' 
                       : 'bg-card text-muted-foreground border-border hover:border-nyt-accent hover:text-nyt-accent'
                   }`}
                 >
                   {btn.label}
                 </button>
               ))}
            </div>
          </div>
        </header>

        <div className="sources-grid">
          <div className="sources-main">
            <section className="mb-12 p-6 border border-border bg-secondary/30 rounded-lg">
              <h2 className="text-sm font-black uppercase tracking-widest text-nyt-accent mb-4 flex items-center gap-2">
                <ShieldCheck size={16} /> Методологија на Доверба
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-secondary-foreground leading-relaxed">
                <div>
                  <h3 className="font-bold text-foreground mb-2">1. Категоризација</h3>
                  <p>Изворите се делат на Агенциски, Јавни сервиси, Независни и Алтернативни. Секоја категорија има различен влезен 'кредибилитет'.</p>
                </div>
                <div>
                  <h3 className="font-bold text-foreground mb-2">2. Квалитетен Индекс (QI)</h3>
                  <p>QI ги спојува брзината, точноста и плурализмот. Оценката 1.00 претставува оптимален баланс меѓу прва објава и кохерентност со другите извори.</p>
                </div>
                <div>
                  <h3 className="font-bold text-foreground mb-2">3. Пондериран Влез</h3>
                  <p>Вестите од извори со 'Висока доверба' имаат поголема тежина при формирање на водечката приказна на насловната страна.</p>
                </div>
              </div>
            </section>

            {loading ? (
              <div className="space-y-12">
                <section>
                  <div className="h-6 w-48 bg-secondary/50 rounded animate-pulse mb-6"></div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {[...Array(6)].map((_, i) => (
                      <div key={i} className="p-6 border border-border bg-card rounded-lg space-y-4">
                        <div className="flex justify-between">
                          <div className="space-y-2">
                            <div className="h-5 w-32 bg-secondary/50 rounded animate-pulse"></div>
                            <div className="h-3 w-20 bg-secondary/50 rounded animate-pulse"></div>
                          </div>
                          <div className="h-6 w-24 bg-secondary/50 rounded animate-pulse"></div>
                        </div>
                        <div className="h-16 w-full bg-secondary/30 rounded animate-pulse"></div>
                        <div className="grid grid-cols-3 gap-2">
                          <div className="h-10 bg-secondary/20 rounded animate-pulse"></div>
                          <div className="h-10 bg-secondary/20 rounded animate-pulse"></div>
                          <div className="h-10 bg-secondary/20 rounded animate-pulse"></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            ) : error ? (
              <div className="py-20 text-center border border-dashed border-nyt-red/30 bg-nyt-red/5">
                <p className="text-nyt-red font-serif italic mb-4">{error}</p>
                <button onClick={() => window.location.reload()} className="nyt-section-label text-nyt-accent underline">
                  Обидете се повторно
                </button>
              </div>
            ) : (
              <div className="space-y-12">
                <section className="sources-section">
                  <div className="mb-5 border-b border-border pb-3">
                    <h2 className="sources-section-title">Македонски Медиуми</h2>
                    <p className="mt-2 max-w-2xl font-nyt-body text-sm leading-relaxed text-secondary-foreground">
                      Главниот домашен екосистем што најчесто ја поставува дневната слика, од агенциски до телевизиски и независни редакции.
                    </p>
                  </div>
                  <div className="source-reputation-grid">
                    {mkSources.map(renderSourceCard)}
                    {mkSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                  </div>
                </section>

                <section className="sources-section">
                  <div className="mb-5 border-b border-border pb-3">
                    <h2 className="sources-section-title">Меѓународни Медиуми</h2>
                    <p className="mt-2 max-w-2xl font-nyt-body text-sm leading-relaxed text-secondary-foreground">
                      Извори што внесуваат надворешен сигнал и поширок контекст, особено кога домашното покривање се потпира на агенции и глобални редакции.
                    </p>
                  </div>
                  <div className="source-reputation-grid">
                    {intSources.map(renderSourceCard)}
                    {intSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                  </div>
                </section>
              </div>
            )}
          </div>

          <aside className="sources-rail lg:sticky lg:top-28 self-start">
            <div className="rail-card">
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><ShieldCheck size={14} /> Доверба</h3>
              <p className="rail-copy">
                Нивоата на репутација ги комбинираат основната credibility оценка, моменталниот quality сигнал и реалното присуство во покривањето.
              </p>
              <div className="source-mini-stats">
                <div><span>Висока доверба</span><strong>{highTrust}</strong></div>
                <div><span>Вкупно извори</span><strong>{filtered.length}</strong></div>
              </div>
            </div>

            <div className="rail-card rail-card-accent">
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><Zap size={14} /> Први На Приказната</h3>
              <p className="rail-copy mb-4">
                Овие извори најчесто први отвораат тема во последниот период.
              </p>
              <div className="source-fast-list">
                {fastMovers.map((source) => (
                  <div key={source.source} className="source-fast-row">
                    <span>{source.source}</span>
                    <strong>{source.speed_first_count}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="rail-card">
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><LineChart size={14} /> Како Да Се Чита</h3>
              <p className="rail-copy mb-5">
                Висока доверба не значи секогаш прв извор. Гледајте ги заедно: колку често водат, колку често подоцна се потврдуваат и колку често остануваат сами.
              </p>
              <div className="space-y-5">
                <div>
                  <p className="mb-2 font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                    <ShieldCheck size={12} /> Најчесто потврдени
                  </p>
                  <div className="source-fast-list">
                    {bestCorroborated.map((source) => (
                      <div key={source.source} className="source-fast-row">
                        <span>{source.source}</span>
                        <strong>{formatPercent(source.corroboration_rate)}</strong>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                    <ShieldAlert size={12} /> Често остануваат сами
                  </p>
                  <div className="source-fast-list">
                    {loneLeaders.map((source) => (
                      <div key={source.source} className="source-fast-row">
                        <span>{source.source}</span>
                        <strong>{formatPercent(source.lone_lead_rate)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default IzvoriPage;
