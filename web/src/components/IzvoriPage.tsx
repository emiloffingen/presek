import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, ShieldCheck, Zap, Activity, ChevronRight } from 'lucide-react';
import { useTranslations } from '../i18n/utils';
import type { ui } from '../i18n/ui';

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

const IzvoriPage: React.FC<{ lang?: keyof typeof ui }> = ({ lang = 'sr' }) => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTier, setFilterTier] = useState<string>('all');
  const t = useTranslations(lang);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${apiBaseUrl()}/sources?t=${Date.now()}`);
        if (!res.ok) {
          setError(t('sources.connection_error'));
          return;
        }
        const allRes = await res.json();
        setSources(allRes);
      } catch {
        setError(t('sources.connection_error'));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [lang, t]);

  const filtered = useMemo(() => {
    let results = sources;
    const q = searchTerm.trim().toLowerCase();
    if (q) results = results.filter((s) => s.source?.toLowerCase().includes(q));
    if (filterTier === 'high') results = results.filter(s => s.trust_tier === 'Visoko poverenje' || s.trust_tier === 'Висока доверба');
    else if (filterTier === 'verified') results = results.filter(s => s.trust_tier === 'Potvrden izvor' || s.trust_tier === 'Потврден извор');
    return results;
  }, [sources, searchTerm, filterTier]);

  const mkSources = filtered.filter((s) => lang === 'mk' ? (s.country === 'MK') : (s.country === 'RS' || !s.country));
  const intSources = filtered.filter((s) => lang === 'mk' ? (s.country !== 'MK') : (s.country && s.country !== 'RS'));
  const fastMovers = [...filtered].sort((a, b) => b.speed_first_count - a.speed_first_count).slice(0, 10);

  const renderSourceRow = (source: SourceRow) => {
    const health = getHealthStatus(source.last_fetched);
    const reliabilityIndex = ((source.corroboration_rate * 0.7) + ((source.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);

    return (
      <a key={source.source} href={`${lang === 'mk' ? '/mk' : ''}/?source=${encodeURIComponent(source.source)}`} className="editorial-source-item group no-underline">
        <div className="item-main">
          <div className="item-head mb-2">
            <div className={`health-dot ${health}`} title={health === 'active' ? t('sources.health_active') : health === 'stale' ? t('sources.health_stale') : t('sources.health_critical')}></div>
            <h3 className="section-heading group-hover:text-nyt-accent transition-colors">{source.source}</h3>
            {(source.trust_tier === 'Visoko poverenje' || source.trust_tier === 'Висока доверба') && (
                <ShieldCheck size={14} className="text-nyt-accent" />
            )}
          </div>
          <p className="item-tendency font-nyt-body text-sm text-muted-foreground line-clamp-1 mb-2 md:mb-3">{source.tendency}</p>
          <div className="item-meta flex items-center gap-2 md:gap-[var(--grid-gap)]">
            <span className="px-2 py-0.5 bg-foreground text-background font-sans text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest">{source.country || (lang === 'mk' ? 'MK' : 'RS')}</span>
            <div className="flex gap-1.5">
                {source.top_categories?.slice(0, 2).map(cat => (
                    <span key={cat} className="px-2 py-0.5 border border-border rounded-sm font-sans text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground/80">{cat}</span>
                ))}
            </div>
            <span className="font-sans text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground/40 ml-auto flex items-center gap-1.5">
                <Activity size={10} /> {formatLastFetched(source.last_fetched)}
            </span>
          </div>
        </div>
        <div className="item-stats flex items-center justify-end gap-3 md:gap-[var(--grid-gap)] ml-auto flex-1 min-w-[200px]">
          <div className="flex gap-3 md:gap-[var(--grid-gap)]">
            <div className="stat-box flex flex-col items-end">
              <span className="text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground mb-0.5">{t('sources.news_24h')}</span>
              <strong className="text-base md:text-lg font-black tabular-nums leading-none">{source.recent_volume}</strong>
            </div>
            <div className="stat-box flex flex-col items-end text-nyt-accent">
              <span className="text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest opacity-60 mb-0.5">{t('sources.quality')}</span>
              <strong className="text-base md:text-lg font-black tabular-nums leading-none">{reliabilityIndex}</strong>
            </div>
          </div>

          <div className="heatmap-container flex gap-[2px] items-end h-8 shrink-0" title={t('sources.activity_30d')}>
            {Array.from({ length: 30 }).map((_, i) => {
                const isRecent = i >= 28;
                const avgVolume = Math.max(1, (source.recent_7d_volume || 0) / 7);
                const noise = Math.sin((i + source.source.length) * 0.5) * 0.3 + 0.8;
                let baseVol = isRecent ? (source.recent_volume || 0) : (source.previous_7d_volume / 7 || avgVolume);
                baseVol = baseVol * noise * (1 + (i / 30) * 0.2);

                const value = Math.max(0.1, baseVol / (avgVolume * 2));

                let bgClass = 'bg-foreground';
                let opacity = 'opacity-20';
                if (value > 0.8) opacity = 'opacity-100';
                else if (value > 0.5) opacity = 'opacity-60';
                else if (value > 0.2) opacity = 'opacity-40';

                if (source.trust_tier === 'Visoko poverenje' || source.trust_tier === 'Висока доверба') bgClass = 'bg-emerald-500';
                else if (source.trust_tier === 'Potvrden izvor' || source.trust_tier === 'Потврден извор') bgClass = 'bg-nyt-accent';

                const height = Math.min(100, Math.max(15, value * 100));

                return (
                    <div
                        key={i}
                        className={`w-[3px] md:w-1.5 rounded-t-[1px] ${bgClass} ${opacity} hover:opacity-100 transition-opacity cursor-crosshair`}
                        style={{ height: `${height}%` }}
                    />
                );
            })}
          </div>
        </div>
      </a>
    );
  };

  return (
    <div className="broadsheet-sources pt-8 md:pt-12">
      <header className="editorial-masthead mb-10 md:mb-16 border-t border-foreground pt-4">
        <div className="masthead-top mb-6 md:mb-8">
          <span className="masthead-kicker font-sans text-[10px] font-black uppercase tracking-[0.25em] text-nyt-accent">{t('sources.reputation')}</span>
        </div>
        <div className="masthead-main mb-8 md:mb-12">
          <h1 className="masthead-title font-serif text-4xl md:text-7xl font-black leading-[0.92] tracking-tighter">{t('sources.title').split(' ')[0]} <span className="text-nyt-accent italic font-light">{t('sources.title').split(' ')[1]}</span></h1>
          <p className="mt-4 md:mt-6 font-serif text-lg md:text-xl italic text-muted-foreground leading-snug max-w-2xl">
            {t('sources.desc')}
          </p>
        </div>

        <div className="masthead-controls sticky top-[72px] z-30 bg-background/80 backdrop-blur-xl border-y border-border py-3 md:py-4 flex flex-col md:flex-row justify-between items-center gap-3 md:gap-[var(--grid-gap)]">
          <div className="relative w-full md:w-96 group">
            <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={t('sources.search_placeholder')}
                className="w-full bg-secondary/20 border-b-2 border-border py-2 pl-2 pr-10 font-serif font-bold text-base md:text-lg outline-none focus:border-nyt-accent placeholder:italic placeholder:font-normal placeholder:opacity-40 transition-all"
            />
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none opacity-40">
                <Search size={18} />
            </div>
          </div>

          <div className="filter-group flex w-full md:w-auto p-1 bg-secondary/30 rounded-lg border border-border shadow-sm">
            {[
                { id: 'all', label: t('sources.all') },
                { id: 'high', label: t('sources.high_trust') },
                { id: 'verified', label: t('sources.verified') }
            ].map(t_tier => (
              <button
                key={t_tier.id}
                onClick={() => setFilterTier(t_tier.id)}
                className={`flex-1 md:flex-none px-3 md:px-4 py-2 rounded-md font-sans text-[9px] md:text-[10px] font-black tracking-[0.14em] md:tracking-widest transition-all ${
                    filterTier === t_tier.id
                    ? 'bg-nyt-accent text-white shadow-md'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t_tier.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="broadsheet-grid">
        <div className="broadsheet-main">
          {loading ? (
            <div className="py-32 text-center opacity-30"><Activity size={48} className="animate-spin mx-auto text-nyt-accent" /></div>
          ) : error ? (
            <div className="py-24 text-center border-2 border-dashed border-border rounded-2xl">
                <h2 className="font-serif text-2xl italic text-muted-foreground">{error}</h2>
            </div>
          ) : (
            <div className="space-y-14 md:space-y-24">
              <section>
                <h2 className="section-heading mb-6 md:mb-10 pb-2 md:pb-3 border-b-4 border-foreground">{lang === 'mk' ? t('sources.mk_media') : t('sources.sr_media')}</h2>
                <div className="flex flex-col">
                  {mkSources.map(renderSourceRow)}
                </div>
              </section>
              <section>
                <h2 className="section-heading mb-6 md:mb-10 pb-2 md:pb-3 border-b-4 border-foreground">{t('sources.intl_signals')}</h2>
                <div className="flex flex-col">
                  {intSources.map(renderSourceRow)}
                </div>
              </section>
            </div>
          )}
        </div>

        <aside className="broadsheet-rail pl-0 md:pl-4">
          <section className="rail-module mb-8 md:mb-12 p-4 md:p-8 bg-nyt-accent/5 border border-nyt-accent/10 rounded-xl">
            <span className="block font-sans text-[9px] md:text-[10px] font-black uppercase tracking-[0.16em] md:tracking-[0.2em] text-nyt-accent mb-3 md:mb-4">{t('briefing.system_balance')}</span>
            <h3 className="section-heading mb-4 leading-tight tracking-tight">{t('sources.qi_title')}</h3>
            <p className="font-nyt-body text-sm leading-relaxed text-muted-foreground">
              {t('sources.qi_desc')}
            </p>
          </section>

          <section className="rail-module mb-8 md:mb-12">
            <h3 className="font-sans text-[10px] md:text-[11px] font-black uppercase tracking-[0.16em] md:tracking-[0.2em] text-foreground mb-4 md:mb-6 pb-2 border-b-2 border-foreground">{t('sources.fastest_today')}</h3>
            <div className="flex flex-col gap-1">
              {fastMovers.map(s => (
                <div key={s.source} className="flex items-center justify-between py-2 border-b border-border/40 hover:bg-secondary/10 px-1 transition-all gap-2">
                  <span className="font-serif font-bold text-sm md:text-base">{s.source}</span>
                  <span className="font-sans text-[10px] md:text-[11px] font-black text-nyt-accent bg-nyt-accent/10 px-2 py-0.5 rounded">+{s.speed_first_count}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="rail-methodology-module p-4 md:p-6 bg-secondary/10 border border-border/40 rounded-sm">
            <h4 className="font-sans text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest border-b border-border pb-3 mb-4">{t('sources.methodology')}</h4>
            <ul className="space-y-3 md:space-y-4">
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest text-foreground">{t('sources.trust')}</span>
                <span className="text-xs text-muted-foreground leading-snug">
                  {t('sources.trust_desc')}
                </span>
              </li>
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest text-foreground">{t('sources.leadership')}</span>
                <span className="text-xs text-muted-foreground leading-snug">
                  {t('sources.leadership_desc')}
                </span>
              </li>
              <li className="flex flex-col gap-1">
                <span className="font-sans text-[8px] md:text-[9px] font-black uppercase tracking-[0.14em] md:tracking-widest text-foreground">{t('sources.confirmation')}</span>
                <span className="text-xs text-muted-foreground leading-snug">
                  {t('sources.confirmation_desc')}
                </span>
              </li>
            </ul>
          </div>
        </aside>
      </div>

      <style>{`
        .editorial-source-item { display: flex; justify-content: space-between; align-items: center; padding: 1.35rem 0; border-bottom: 1px solid var(--border); transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        .editorial-source-item:hover { background: color-mix(in srgb, var(--background) 96%, var(--nyt-accent) 4%); padding-left: 1rem; padding-right: 1rem; margin-left: -1rem; margin-right: -1rem; border-radius: 0px; border-bottom-color: var(--nyt-accent); }
        .item-main { flex: 1; min-width: 0; }
        .item-head { display: flex; align-items: center; gap: 0.75rem; }
        .health-dot { width: 6px; height: 6px; border-radius: 50%; }
        .health-dot.active { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
        .health-dot.stale { background: #f59e0b; }
        .health-dot.critical { background: #ef4444; }

        .broadsheet-grid { display: grid; grid-template-columns: 1fr; gap: 3rem; }
        @media (min-width: 1024px) {
          .broadsheet-grid { grid-template-columns: 1fr; }
          .broadsheet-rail {   align-self: start; }
        }

        @media (max-width: 768px) {
          .editorial-source-item { flex-direction: column; align-items: flex-start; gap: 1rem; }
          .editorial-source-item:hover { padding-left: 0.5rem; padding-right: 0.5rem; margin-left: -0.5rem; margin-right: -0.5rem; }
          .item-head { gap: 0.5rem; }
          .item-meta { flex-wrap: wrap; }
          .item-meta > span:last-child { width: 100%; margin-left: 0 !important; }
          .item-stats { margin-left: 0 !important; width: 100%; border-top: 1px solid var(--border); padding-top: 0.8rem; min-width: 0; justify-content: space-between; }
          .masthead-controls { flex-direction: column; align-items: stretch; gap: 0.75rem; }
          .filter-group { width: 100%; }
        }

        @media (max-width: 639px) {
          .broadsheet-grid { gap: 1.5rem; }
          .section-heading { font-size: 1.25rem; line-height: 1.05; }
          .item-tendency { font-size: 0.88rem; }
          .heatmap-container { height: 1.6rem; }
        }
      `}</style>
    </div>
  );
};

export default IzvoriPage;
