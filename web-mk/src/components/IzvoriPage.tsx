import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, ShieldCheck, Zap, Activity, ChevronRight } from 'lucide-react';

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
  if (!value) return 'Nema svez signal';
  try {
    const date = new Date(value);
    return date.toLocaleString('mk-MK', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return 'Nema svez signal';
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
          setError('Neuspesno povrzuvanje.');
          return;
        }
        const allRes = await res.json();
        setSources(allRes);
      } catch {
        setError('Neuspesno povrzuvanje.');
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
    if (filterTier === 'high') results = results.filter(s => s.trust_tier === 'Visoko poverenje');
    else if (filterTier === 'verified') results = results.filter(s => s.trust_tier === 'Potvrden izvor');
    return results;
  }, [sources, searchTerm, filterTier]);

  const mkSources = filtered.filter((s) => s.country === 'RS' || !s.country);
  const intSources = filtered.filter((s) => s.country && s.country !== 'RS');
  const fastMovers = [...filtered].sort((a, b) => b.speed_first_count - a.speed_first_count).slice(0, 10);

  const renderSourceRow = (source: SourceRow) => {
    const health = getHealthStatus(source.last_fetched);
    const reliabilityIndex = ((source.corroboration_rate * 0.7) + ((source.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);
    
    return (
      <a key={source.source} href={`/?source=${encodeURIComponent(source.source)}`} className="editorial-source-item group no-underline">
        <div className="item-main">
          <div className="item-head mb-2">
            <div className={`health-dot ${health}`} title={health === 'active' ? 'Azurirano neodamna' : health === 'stale' ? 'Postojat docnenja' : 'Nema svez signal'}></div>
            <h3 className="item-title font-serif text-2xl font-black group-hover:text-nyt-accent transition-colors">{source.source}</h3>
            {source.trust_tier === 'Visoko poverenje' && (
                <ShieldCheck size={14} className="text-nyt-accent" />
            )}
          </div>
          <p className="item-tendency font-nyt-body text-sm text-muted-foreground line-clamp-1 mb-3">{source.tendency}</p>
          <div className="item-meta flex items-center gap-3">
            <span className="px-2 py-0.5 bg-foreground text-background font-sans text-[9px] font-black uppercase tracking-widest">{source.country || 'RS'}</span>
            <div className="flex gap-1.5">
                {source.top_categories?.slice(0, 2).map(cat => (
                    <span key={cat} className="px-2 py-0.5 border border-border rounded-sm font-sans text-[9px] font-black uppercase tracking-widest text-muted-foreground/80">{cat}</span>
                ))}
            </div>
            <span className="font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground/40 ml-auto flex items-center gap-1.5">
                <Activity size={10} /> {formatLastFetched(source.last_fetched)}
            </span>
          </div>
        </div>
        <div className="item-stats grid grid-cols-3 gap-6 ml-12">
          <div className="stat-box flex flex-col items-center">
            <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">QI</span>
            <strong className="text-xl font-black tabular-nums">{reliabilityIndex}</strong>
          </div>
          <div className="stat-box flex flex-col items-center">
            <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">24C</span>
            <strong className="text-xl font-black tabular-nums">{source.recent_volume}</strong>
          </div>
          <div className="stat-box flex flex-col items-center text-nyt-accent">
            <span className="text-[9px] font-black uppercase tracking-widest opacity-60 mb-1">PRV</span>
            <strong className="text-xl font-black tabular-nums">{source.speed_first_count}</strong>
          </div>
        </div>
      </a>
    );
  };

  return (
    <div className="broadsheet-sources pt-12">
      <header className="editorial-masthead mb-16 border-t border-foreground pt-4">
        <div class="masthead-top mb-8">
          <span className="masthead-kicker font-sans text-[10px] font-black uppercase tracking-[0.25em] text-nyt-accent">MEDIUMSKA REPUTACIJA</span>
        </div>
        <div className="masthead-main mb-12">
          <h1 className="masthead-title font-serif text-5xl md:text-7xl font-black leading-[0.9] tracking-tighter">Mediumski <span className="text-nyt-accent italic font-light">izvori</span></h1>
          <p className="mt-6 font-serif text-xl italic text-muted-foreground leading-snug max-w-2xl">Rangiranje i detalna statistika na site mediumi sto Presek im sledi — po aktivnost, brzina i doverlivost.</p>
        </div>
        
        <div className="masthead-controls sticky top-[72px] z-30 bg-background/80 backdrop-blur-xl border-y border-border py-4 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="relative w-full md:w-96 group">
            <input 
                type="text" 
                value={searchTerm} 
                onChange={(e) => setSearchTerm(e.target.value)} 
                placeholder="Prebaraj redakcii..." 
                className="w-full bg-secondary/20 border-b-2 border-border py-2 pl-2 pr-10 font-serif font-bold text-lg outline-none focus:border-nyt-accent placeholder:italic placeholder:font-normal placeholder:opacity-40 transition-all"
            />
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none opacity-40">
                <Search size={18} />
            </div>
          </div>
          
          <div className="filter-group flex p-1 bg-secondary/30 rounded-lg border border-border shadow-sm">
            {[
                { id: 'all', label: 'SITE' },
                { id: 'high', label: 'Visoko poverenje' },
                { id: 'verified', label: 'potvrdeni' }
            ].map(t => (
              <button 
                key={t.id} 
                onClick={() => setFilterTier(t.id)} 
                className={`px-4 py-2 rounded-md font-sans text-[10px] font-black tracking-widest transition-all ${
                    filterTier === t.id 
                    ? 'bg-nyt-accent text-white shadow-md' 
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="broadsheet-grid">
        <div className="broadsheet-main pr-12 border-r border-border/40">
          {loading ? (
            <div className="py-32 text-center opacity-30"><Activity size={48} className="animate-spin mx-auto text-nyt-accent" /></div>
          ) : error ? (
            <div className="py-24 text-center border-2 border-dashed border-border rounded-2xl">
                <h2 className="font-serif text-2xl italic text-muted-foreground">{error}</h2>
            </div>
          ) : (
            <div className="space-y-24">
              <section>
                <h2 className="font-serif text-3xl font-black italic mb-10 pb-3 border-b-4 border-foreground">Makedonski Mediumi</h2>
                <div className="flex flex-col">
                  {mkSources.map(renderSourceRow)}
                </div>
              </section>
              <section>
                <h2 className="font-serif text-3xl font-black italic mb-10 pb-3 border-b-4 border-foreground">Medjunarodni Signali</h2>
                <div className="flex flex-col">
                  {intSources.map(renderSourceRow)}
                </div>
              </section>
            </div>
          )}
        </div>

        <aside className="broadsheet-rail pl-4">
          <section className="rail-module mb-12 p-8 bg-nyt-accent/5 border border-nyt-accent/10 rounded-xl">
            <span className="block font-sans text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent mb-4">SISTEMSKI UVID</span>
            <h3 className="font-serif text-2xl font-black leading-tight mb-4 tracking-tight">KVALITETEN INDEKS (QI)</h3>
            <p className="font-nyt-body text-sm leading-relaxed text-muted-foreground">QI im spojuva brzinata, tocnosta i pluralizmot. Presmetano preku nasiot <strong>sistem za dlaboka analiza</strong>. Ocenkata 1.00 pretstavuva optimalen balans na pazarot.</p>
          </section>

          <section className="rail-module mb-12">
            <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.2em] text-foreground mb-6 pb-2 border-b-2 border-foreground">NAJBRZI denes</h3>
            <div className="flex flex-col gap-1">
              {fastMovers.map(s => (
                <div key={s.source} className="flex items-center justify-between py-2.5 border-b border-border/40 hover:bg-secondary/10 px-1 transition-all">
                  <span className="font-serif font-bold text-base">{s.source}</span>
                  <span className="font-sans text-[11px] font-black text-nyt-accent bg-nyt-accent/10 px-2 py-0.5 rounded">+{s.speed_first_count}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="rail-methodology-module p-6 bg-secondary/10 border border-border/40 rounded-sm">
            <h4 className="font-sans text-[10px] font-black uppercase tracking-widest border-b border-border pb-3 mb-4">METODOLOGIJA</h4>
            <ul className="space-y-4">
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[9px] font-black uppercase tracking-widest text-foreground">Doverba</span>
                <span className="text-xs text-muted-foreground leading-snug">Пондериран удел на основа на историска точност и стабилност на известување.</span>
              </li>
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[9px] font-black uppercase tracking-widest text-foreground">Vodstvo</span>
                <span className="text-xs text-muted-foreground leading-snug">Kolku cesto mediumot prv otvora tema sto podocna stanuva dominantna.</span>
              </li>
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[9px] font-black uppercase tracking-widest text-foreground">Potvrda</span>
                <span className="text-xs text-muted-foreground leading-snug">Stapka na prifacanje i potvrda na vesta od drugi nezavisni izvori.</span>
              </li>
            </ul>
          </div>
        </aside>
      </div>

      <style>{`
        .editorial-source-item { display: flex; justify-content: space-between; align-items: center; padding: 2rem 0; border-bottom: 1px solid var(--border); transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        .editorial-source-item:hover { background: color-mix(in srgb, var(--background) 96%, var(--nyt-accent) 4%); padding-left: 1rem; padding-right: 1rem; margin-left: -1rem; margin-right: -1rem; border-radius: 4px; border-bottom-color: var(--nyt-accent); }
        .item-main { flex: 1; min-width: 0; }
        .item-head { display: flex; align-items: center; gap: 0.75rem; }
        .health-dot { width: 6px; height: 6px; border-radius: 50%; }
        .health-dot.active { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
        .health-dot.stale { background: #f59e0b; }
        .health-dot.critical { background: #ef4444; }

        .broadsheet-grid { display: grid; grid-template-columns: 1fr; gap: 3rem; }
        @media (min-width: 1024px) {
          .broadsheet-grid { grid-template-columns: minmax(0, 1fr) 320px; }
          .broadsheet-rail { position: sticky; top: 8rem; align-self: start; }
        }

        @media (max-width: 768px) {
          .editorial-source-item { flex-direction: column; align-items: flex-start; gap: 1.5rem; }
          .item-stats { margin-left: 0 !important; width: 100%; border-top: 1px solid var(--border); padding-top: 1rem; }
          .masthead-controls { flex-direction: column; align-items: stretch; gap: 1.5rem; }
        }
      `}</style>
    </div>
  );
};

export default IzvoriPage;
