import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, Loader2, Info, ShieldCheck, Zap, Activity, LineChart, ShieldAlert } from 'lucide-react';

interface SourceRow {
  source: string;
  country: string;
  category: string;
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

export const IzvoriPage: React.FC = () => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

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
    const q = searchTerm.trim().toLowerCase();
    if (!q) return sources;
    return sources.filter((source) => source.source?.toLowerCase().includes(q));
  }, [sources, searchTerm]);

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

  const renderSourceCard = (source: SourceRow) => (
    <a key={source.source} href={`/?q=${encodeURIComponent(source.source)}`} className="source-reputation-card">
      <div className="source-reputation-top">
        <div>
          <h3 className="source-reputation-name">{source.source}</h3>
          <p className="source-reputation-meta">{source.category || 'Општо'} · {source.country || 'МК'}</p>
        </div>
        <span className={`source-tier ${tierClass(source.trust_tier)}`}>{source.trust_tier}</span>
      </div>

      <p className="source-reputation-copy">{source.tendency}</p>
      <p className={`source-trend-note ${trendClass(source.trend_label)}`}>
        <span>{source.trend_label}</span>
        <strong>{source.trend_delta >= 0 ? `+${source.trend_delta}` : source.trend_delta} во 7 дена</strong>
      </p>

      <div className="source-reputation-stats">
        <div>
          <span>24ч обем</span>
          <strong>{source.recent_volume}</strong>
        </div>
        <div>
          <span>Прв на сторија</span>
          <strong>{source.speed_first_count}</strong>
        </div>
        <div>
          <span>Тежина</span>
          <strong>{source.effective_weight.toFixed(2)}</strong>
        </div>
      </div>

      <div className="source-history-grid">
        <div>
          <span>Потврдени водства</span>
          <strong>{formatPercent(source.corroboration_rate)}</strong>
        </div>
        <div>
          <span>Соло водства</span>
          <strong>{formatPercent(source.lone_lead_rate)}</strong>
        </div>
        <div>
          <span>Водства 30д</span>
          <strong>{source.lead_count_30d}</strong>
        </div>
        <div>
          <span>7д тренд</span>
          <strong>{source.recent_7d_volume}</strong>
        </div>
      </div>

      <div className="source-reputation-footer">
        <span>{formatLastFetched(source.last_fetched)}</span>
        {!source.is_active && <span className="source-status-paused">Паузиран</span>}
      </div>
    </a>
  );

  return (
    <div className="bg-background text-foreground">
      <div className="site-layout py-8">
        <header className="sources-header">
          <span className="sources-kicker">Репутација</span>
          <h1 className="sources-headline">Медиумски Извори</h1>
          <p className="sources-intro">
            Преглед на изворите што Пресек ги следи, со ниво на доверба, дневен ритам, сигнал за брзина и присуство во покривањето.
          </p>
          <div className="max-w-md mt-6 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Пребарај извори..."
              className="w-full bg-secondary border border-border pl-10 pr-4 py-2 text-sm text-foreground focus:outline-none focus:border-nyt-accent transition-colors rounded-full"
            />
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
                  <h3 className="font-bold text-foreground mb-2">2. Кохерентност</h3>
                  <p>Системот ја мери 'стапката на потврда'. Колку почесто веста на еден медиум се совпаѓа со другите, толку е повисок неговиот индекс на стабилност.</p>
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
                  <h2 className="sources-section-title">Македонски Медиуми</h2>
                  <div className="source-reputation-grid">
                    {mkSources.map(renderSourceCard)}
                    {mkSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                  </div>
                </section>

                <section className="sources-section">
                  <h2 className="sources-section-title">Меѓународни Медиуми</h2>
                  <div className="source-reputation-grid">
                    {intSources.map(renderSourceCard)}
                    {intSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                  </div>
                </section>
              </div>
            )}
          </div>

          <aside className="sources-rail">
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
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><LineChart size={14} /> Најчесто Потврдени</h3>
              <div className="source-fast-list">
                {bestCorroborated.map((source) => (
                  <div key={source.source} className="source-fast-row">
                    <span>{source.source}</span>
                    <strong>{formatPercent(source.corroboration_rate)}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="rail-card">
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><ShieldAlert size={14} /> Често Остануваат Сами</h3>
              <div className="source-fast-list">
                {loneLeaders.map((source) => (
                  <div key={source.source} className="source-fast-row">
                    <span>{source.source}</span>
                    <strong>{formatPercent(source.lone_lead_rate)}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="rail-card">
              <h3 className="rail-card-title flex items-center gap-2 mb-4"><Activity size={14} /> Како Да Се Чита</h3>
              <p className="rail-copy">
                Висока доверба не значи секогаш прв извор. Гледајте ги заедно: колку често водат, колку често подоцна се потврдуваат и колку често остануваат сами.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default IzvoriPage;
