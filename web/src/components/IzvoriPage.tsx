import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, ShieldCheck, Zap, Activity, LineChart, ShieldAlert, ChevronRight } from 'lucide-react';

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

const IzvoriPage: React.FC = () => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTier, setFilterTier] = useState<string>('all');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${apiBaseUrl()}/sources?t=${Date.now()}`);
        if (!res.ok) {
          setError('Неуспешно поврзување.');
          return;
        }
        const allRes = await res.json();
        setSources(allRes);
      } catch {
        setError('Неуспешно поврзување.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filtered = useMemo(() => {
    let results = sources;
    const q = searchTerm.trim().toLowerCase();
    if (q) results = results.filter((s) => s.source?.toLowerCase().includes(q));
    if (filterTier === 'high') results = results.filter(s => s.trust_tier === 'Висока доверба');
    else if (filterTier === 'verified') results = results.filter(s => s.trust_tier === 'Потврден извор');
    return results;
  }, [sources, searchTerm, filterTier]);

  const mkSources = filtered.filter((s) => s.country === 'MK' || !s.country);
  const intSources = filtered.filter((s) => s.country && s.country !== 'MK');
  const fastMovers = [...filtered].sort((a, b) => b.speed_first_count - a.speed_first_count).slice(0, 6);

  const renderSourceRow = (source: SourceRow) => {
    const health = getHealthStatus(source.last_fetched);
    const reliabilityIndex = ((source.corroboration_rate * 0.7) + ((source.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);
    
    return (
      <a key={source.source} href={`/?q=${encodeURIComponent(source.source)}`} className="editorial-source-item group">
        <div className="item-main">
          <div className="item-head">
            <div className={`health-dot ${health}`}></div>
            <h3 className="item-title">{source.source}</h3>
            <span className="item-tier">{source.trust_tier}</span>
          </div>
          <p className="item-tendency">{source.tendency}</p>
          <div className="item-meta">
            <span className="meta-tag">{source.country || 'MK'}</span>
            {source.top_categories?.slice(0, 2).map(cat => <span key={cat} className="meta-tag-outline">{cat}</span>)}
            <span className="meta-time">{formatLastFetched(source.last_fetched)}</span>
          </div>
        </div>
        <div className="item-stats">
          <div className="stat-box">
            <span>QI</span>
            <strong>{reliabilityIndex}</strong>
          </div>
          <div className="stat-box">
            <span>24ч</span>
            <strong>{source.recent_volume}</strong>
          </div>
          <div className="stat-box accent">
            <span>ПРВ</span>
            <strong>{source.speed_first_count}</strong>
          </div>
        </div>
      </a>
    );
  };

  return (
    <div className="broadsheet-sources">
      <header className="editorial-masthead mb-12">
        <div className="masthead-top">
          <span className="masthead-kicker">МЕДИУМСКА РЕПУТАЦИЈА</span>
        </div>
        <div className="masthead-main">
          <h1 className="masthead-title">Медиумски <span>Извори</span></h1>
        </div>
        <div className="masthead-controls">
          <div className="search-wrap">
            <Search size={16} />
            <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Пребарај редакции..." />
          </div>
          <div className="filter-group">
            {['all', 'high', 'verified'].map(t => (
              <button key={t} onClick={() => setFilterTier(t)} className={filterTier === t ? 'active' : ''}>
                {t === 'all' ? 'СИТЕ' : t === 'high' ? 'ВИСОКА ДОВЕРБА' : 'ПОТВРДЕНИ'}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="broadsheet-grid">
        <div className="broadsheet-main">
          {loading ? (
            <div className="p-12 text-center opacity-30"><Activity className="animate-pulse mx-auto" /></div>
          ) : error ? (
            <div className="empty-state"><h2>{error}</h2></div>
          ) : (
            <div className="space-y-16">
              <section>
                <h2 className="section-title-italic mb-6">Македонски Медиуми</h2>
                <div className="editorial-list">
                  {mkSources.map(renderSourceRow)}
                </div>
              </section>
              <section>
                <h2 className="section-title-italic mb-6">Меѓународни Сигнали</h2>
                <div className="editorial-list">
                  {intSources.map(renderSourceRow)}
                </div>
              </section>
            </div>
          )}
        </div>

        <aside className="broadsheet-rail">
          <section className="rail-block rail-block-alt">
            <p className="rail-kicker">Интелигенција</p>
            <h3 className="rail-title">КВАЛИТЕТЕН ИНДЕКС</h3>
            <p className="rail-text">QI ги спојува брзината, точноста и плурализмот. Оценката 1.00 претставува оптимален баланс на пазарот.</p>
          </section>

          <section className="rail-block">
            <p className="rail-kicker">Сигнал</p>
            <h3 className="rail-title">НАЈБРЗИ ДЕНЕС</h3>
            <div className="rail-directory">
              {fastMovers.map(s => (
                <div key={s.source} className="dir-row">
                  <span className="name">{s.source}</span>
                  <span className="val">+{s.speed_first_count}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="rail-methodology">
            <h4 className="font-sans text-[10px] font-black uppercase tracking-widest border-b border-border pb-2 mb-3">МЕТОДОЛОГИЈА</h4>
            <ul className="space-y-3 text-xs opacity-80 leading-relaxed font-nyt-body">
              <li><strong>Доверба:</strong> Пондериран влез според историска точност.</li>
              <li><strong>Водство:</strong> Колку често медиумот прв отвора тема.</li>
              <li><strong>Потврда:</strong> Стапка на прифаќање на веста од другите.</li>
            </ul>
          </div>
        </aside>
      </div>

      <style>{`
        .broadsheet-sources { width: 100%; }
        .editorial-masthead { border-bottom: 4px solid var(--foreground); padding-bottom: 2rem; margin-bottom: 3rem; }
        .masthead-kicker { font-family: var(--font-sans); font-size: 0.6rem; font-weight: 950; letter-spacing: 0.15em; color: var(--nyt-accent); }
        .masthead-title { font-family: var(--font-serif); font-size: clamp(2.5rem, 6vw, 4.5rem); font-weight: 900; line-height: 0.9; margin: 1.5rem 0; letter-spacing: -0.02em; }
        .masthead-title span { font-weight: 400; font-style: italic; }
        
        .masthead-controls { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1.5rem; margin-top: 2rem; }
        .search-wrap { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 1rem; border: 1px solid var(--foreground); background: var(--background); flex: 1; max-width: 400px; }
        .search-wrap input { background: transparent; border: 0; outline: none; font-family: var(--font-sans); font-size: 0.85rem; font-weight: 700; width: 100%; }
        .filter-group { display: flex; gap: 0.5rem; }
        .filter-group button { font-family: var(--font-sans); font-size: 0.65rem; font-weight: 950; padding: 0.5rem 1rem; border: 1px solid var(--border); background: var(--background); transition: all 0.2s; }
        .filter-group button.active { background: var(--foreground); color: var(--background); border-color: var(--foreground); }

        .broadsheet-grid { display: grid; grid-template-columns: 1fr; gap: 3rem; }
        @media (min-width: 1024px) {
          .broadsheet-grid { grid-template-columns: minmax(0, 1fr) 300px; }
          .broadsheet-main { border-right: 1px solid var(--border); padding-right: 3rem; }
          .broadsheet-rail { position: sticky; top: 8rem; align-self: start; }
        }

        .section-title-italic { font-family: var(--font-serif); font-size: 1.8rem; font-weight: 900; font-style: italic; border-bottom: 1px solid var(--border); padding-bottom: 0.75rem; }

        .editorial-list { display: flex; flex-direction: column; }
        .editorial-source-item { display: flex; justify-content: space-between; align-items: center; padding: 1.5rem 0; border-bottom: 1px solid var(--border); text-decoration: none; color: inherit; transition: background 0.15s; }
        .editorial-source-item:hover { background: color-mix(in srgb, var(--background) 97%, var(--nyt-accent) 3%); }
        .item-main { flex: 1; }
        .item-head { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }
        .health-dot { width: 6px; height: 6px; border-radius: 50%; }
        .health-dot.active { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
        .health-dot.stale { background: #f59e0b; }
        .health-dot.critical { background: #ef4444; }
        .item-title { font-family: var(--font-serif); font-size: 1.25rem; font-weight: 850; }
        .item-tier { font-family: var(--font-sans); font-size: 0.6rem; font-weight: 950; text-transform: uppercase; color: var(--nyt-accent); padding: 0.1rem 0.4rem; border: 1px solid var(--nyt-accent); }
        .item-tendency { font-family: var(--font-nyt-body); font-size: 0.95rem; color: var(--secondary-foreground); margin-bottom: 0.75rem; line-height: 1.4; }
        .item-meta { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
        .meta-tag { font-family: var(--font-sans); font-size: 0.55rem; font-weight: 950; background: var(--foreground); color: var(--background); padding: 0.1rem 0.4rem; }
        .meta-tag-outline { font-family: var(--font-sans); font-size: 0.55rem; font-weight: 850; border: 1px solid var(--border); padding: 0.1rem 0.4rem; color: var(--muted-foreground); }
        .meta-time { font-family: var(--font-sans); font-size: 0.6rem; font-weight: 800; opacity: 0.5; }

        .item-stats { display: flex; gap: 1.5rem; }
        .stat-box { text-align: center; min-width: 3rem; }
        .stat-box span { font-family: var(--font-sans); font-size: 0.55rem; font-weight: 950; color: var(--muted-foreground); display: block; margin-bottom: 0.2rem; }
        .stat-box strong { font-family: var(--font-serif); font-size: 1.25rem; font-weight: 900; }
        .stat-box.accent strong { color: var(--nyt-accent); }

        .rail-block { margin-bottom: 2.5rem; }
        .rail-block-alt { padding: 1.25rem; background: var(--secondary); border-radius: 4px; }
        .rail-kicker { font-family: var(--font-sans); font-size: 0.6rem; font-weight: 950; color: var(--nyt-accent); text-transform: uppercase; margin-bottom: 0.5rem; }
        .rail-title { font-family: var(--font-sans); font-size: 0.75rem; font-weight: 950; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .rail-directory { display: flex; flex-direction: column; }
        .dir-row { display: flex; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid var(--border); }
        .dir-row .name { font-family: var(--font-serif); font-size: 0.9rem; font-weight: 700; }
        .dir-row .val { font-family: var(--font-sans); font-size: 0.65rem; font-weight: 950; color: var(--nyt-accent); }

        @media (max-width: 640px) {
          .item-stats { display: none; }
          .masthead-controls { flex-direction: column; align-items: stretch; }
          .editorial-source-item { padding: 1.25rem 0; }
        }
      `}</style>
    </div>
  );
};

export default IzvoriPage;
