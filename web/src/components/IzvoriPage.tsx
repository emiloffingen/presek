import { homePath, localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Search, ShieldCheck, Zap, Activity, ChevronRight, Globe, Compass, HelpCircle } from 'lucide-react';
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
  paused_at?: string | null;
}

const HIGH_TRUST_TIERS = new Set(['Visoko poverenje', 'Висока доверба']);
const VERIFIED_TIERS = new Set(['Potvrden izvor', 'Потврден извор']);

function formatLastFetched(value: string | undefined, noSignalLabel: string, locale: string) {
  if (!value) return noSignalLabel;
  try {
    const date = new Date(value);
    return date.toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return noSignalLabel;
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

// Media Bias Coordinate Mapper Function
const getCoordinates = (source: SourceRow, lang: string) => {
  let x = 0;
  const name = source.source;
  const cat = source.category || '';
  const weight = source.effective_weight || 1.0;
  
  // Editorial independence/stance mapping (X-axis: Left [-1] represents independent/critical, Right [+1] represents tabloid/aligned)
  if (cat === 'Nezavisni' || cat === 'Istraživački') {
    x = -0.75 - (weight - 1.5) * 0.1;
  } else if (cat === 'Tabloidi') {
    x = 0.75 + (2.0 - weight) * 0.1;
  } else if (cat === 'Javni Servis') {
    x = -0.02;
  } else {
    // Determine stance heuristically from name and weight
    const lowerName = name.toLowerCase();
    if (
      lowerName.includes('danas') ||
      lowerName.includes('n1') ||
      lowerName.includes('nova.rs') ||
      lowerName.includes('krik') ||
      lowerName.includes('insajder') ||
      lowerName.includes('vreme') ||
      lowerName.includes('nedeljnik') ||
      lowerName.includes('cenzolovka') ||
      lowerName.includes('cins') ||
      lowerName.includes('360 stepeni') ||
      lowerName.includes('civil') ||
      lowerName.includes('fokus') ||
      lowerName.includes('frontline') ||
      lowerName.includes('libertas') ||
      lowerName.includes('a1on') ||
      lowerName.includes('nezavisen')
    ) {
      x = -0.7 - (weight >= 1.5 ? 0.12 : 0.04);
    } else if (
      lowerName.includes('kurir') ||
      lowerName.includes('telegraf') ||
      lowerName.includes('informer') ||
      lowerName.includes('alo.rs') ||
      lowerName.includes('novosti') ||
      lowerName.includes('objektiv') ||
      lowerName.includes('sitel') ||
      lowerName.includes('vecer') ||
      lowerName.includes('kanal 5') ||
      lowerName.includes('centar.mk') ||
      lowerName.includes('infomax') ||
      lowerName.includes('zase.mk')
    ) {
      x = 0.7 + (weight < 1.2 ? 0.12 : 0.04);
    } else if (
      lowerName.includes('rts') ||
      lowerName.includes('mrt') ||
      lowerName.includes('mia') ||
      lowerName.includes('politika')
    ) {
      x = 0.02;
    } else {
      if (cat === 'Sport' || cat === 'Tehnologija' || cat === 'Kultura' || cat === 'Zivot') {
        x = -0.1 + (weight - 1.0) * 0.05;
      } else {
        x = 0.2 - (weight - 1.0) * 0.1;
      }
    }
  }

  // Ensure strict bounds
  x = Math.max(-0.95, Math.min(0.95, x));

  // Consistent deterministic dispersion to avoid perfect overlaps
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const jitterX = ((Math.abs(hash) % 100) / 100 - 0.5) * 0.14;
  x = x + jitterX;
  x = Math.max(-0.92, Math.min(0.92, x));

  // Consensus / Concordance mapping (Y-axis: Top [+1] high corroboration consensus, Bottom [-1] exclusive lone leads)
  const cRate = source.corroboration_rate ?? 0.5;
  let y = (cRate - 0.5) * 1.6;
  if (source.lead_count_30d === 0) {
    y = 0.0;
  }
  
  if (cat === 'Istraživački' && y > -0.2) {
    y = y - 0.2;
  }
  
  const jitterY = (((Math.abs(hash) >> 8) % 100) / 100 - 0.5) * 0.14;
  y = y + jitterY;
  y = Math.max(-0.85, Math.min(0.85, y));

  // Translate coordinates to SVG canvas relative percentages
  // X: -1 maps to 8%, +1 maps to 92%
  // Y: +1 maps to 12% (top), -1 maps to 88% (bottom)
  const pctX = 50 + x * 42;
  const pctY = 50 - y * 38;

  return { x, y, pctX, pctY };
};

const IzvoriPage: React.FC<{ lang?: keyof typeof ui }> = ({ lang = 'sr' }) => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTier, setFilterTier] = useState<string>('all');
  const t = useTranslations(lang);
  const dateLocale = lang === 'mk' ? 'mk-MK' : 'sr-RS';
  const defaultCountry = lang === 'mk' ? 'MK' : 'RS';

  // New interactive graph states
  const [graphSearch, setGraphSearch] = useState('');
  const [hoveredSource, setHoveredSource] = useState<SourceRow | null>(null);
  const [selectedSource, setSelectedSource] = useState<SourceRow | null>(null);

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
    if (filterTier === 'high') {
      results = results.filter((s) => HIGH_TRUST_TIERS.has(s.trust_tier));
    } else if (filterTier === 'verified') {
      results = results.filter((s) => VERIFIED_TIERS.has(s.trust_tier));
    }
    return results;
  }, [sources, searchTerm, filterTier]);

  const mkSources = filtered.filter((s) => lang === 'mk' ? (s.country === 'MK') : (s.country === 'RS' || !s.country));
  const intSources = filtered.filter((s) => lang === 'mk' ? (s.country !== 'MK') : (s.country && s.country !== 'RS'));
  const fastMovers = [...filtered].sort((a, b) => b.speed_first_count - a.speed_first_count).slice(0, 10);

  // Filter sources displayed on the domestic graph
  const domesticGraphSources = useMemo(() => {
    return sources.filter((s) => lang === 'mk' ? (s.country === 'MK') : (s.country === 'RS' || !s.country));
  }, [sources, lang]);

  const isMatchedByFilter = (s: SourceRow) => {
    const q = searchTerm.trim().toLowerCase();
    if (q && !s.source.toLowerCase().includes(q)) return false;
    if (filterTier === 'high') {
      if (!HIGH_TRUST_TIERS.has(s.trust_tier)) return false;
    } else if (filterTier === 'verified') {
      if (!VERIFIED_TIERS.has(s.trust_tier)) return false;
    }
    return true;
  };

  const scrollToSource = (sourceName: string) => {
    const id = `source-${encodeURIComponent(sourceName)}`;
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      element.classList.add('highlight-pulse');
      setTimeout(() => {
        element.classList.remove('highlight-pulse');
      }, 2500);
    }
  };

  const renderSourceRow = (source: SourceRow) => {
    const health = getHealthStatus(source.last_fetched);
    const reliabilityIndex = ((source.corroboration_rate * 0.7) + ((source.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);
    const isSelected = selectedSource?.source === source.source;
    const rowId = `source-${encodeURIComponent(source.source)}`;

    return (
      <a
        key={source.source}
        id={rowId}
        href={`${localePathForLang('/', lang)}?source=${encodeURIComponent(source.source)}`}
        className={`editorial-source-item group no-underline transition-all duration-300 ${isSelected ? 'border-l-4 border-l-nyt-accent pl-4 bg-nyt-accent/5' : ''}`}
        onClick={(e) => {
          // If they click on the item directly, let normal navigation run, but record selection state
          setSelectedSource(source);
        }}
      >
        <div className="item-main">
          <div className="item-head mb-2">
            <div className={`health-dot ${health}`} title={health === 'active' ? t('sources.health_active') : health === 'stale' ? t('sources.health_stale') : t('sources.health_critical')}></div>
            <h3 className="section-heading group-hover:text-nyt-accent transition-colors">{source.source}</h3>
            {HIGH_TRUST_TIERS.has(source.trust_tier) && (
              <ShieldCheck size={14} className="text-nyt-accent" />
            )}
          </div>
          <p className="item-tendency font-nyt-body text-sm text-muted-foreground line-clamp-1 mb-2 md:mb-3">{source.tendency}</p>
          <div className="item-meta flex items-center gap-2 md:gap-[var(--grid-gap)]">
            <span className="px-2 py-0.5 bg-foreground text-background font-sans ui-label-min font-black uppercase tracking-[0.14em] md:tracking-widest">{source.country || defaultCountry}</span>
            <div className="flex gap-1.5">
              {source.top_categories?.slice(0, 2).map(cat => (
                <span key={cat} className="px-2 py-0.5 border border-border rounded-none font-sans ui-label-min font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground/80">{cat}</span>
              ))}
            </div>
            <span className="font-sans ui-label-min font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground/40 ml-auto flex items-center gap-1.5">
              <Activity size={10} /> {formatLastFetched(source.last_fetched, t('sources.no_signal'), dateLocale)}
            </span>
          </div>
        </div>
        <div className="item-stats flex items-center justify-end gap-3 md:gap-[var(--grid-gap)] ml-auto flex-1 min-w-[200px]">
          <div className="flex gap-3 md:gap-[var(--grid-gap)]">
            <div className="stat-box flex flex-col items-end">
              <span className="ui-label-min font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground mb-0.5">{t('sources.news_24h')}</span>
              <strong className="text-base md:text-lg font-black tabular-nums leading-none">{source.recent_volume}</strong>
            </div>
            <div className="stat-box flex flex-col items-end text-nyt-accent">
              <span className="ui-label-min font-black uppercase tracking-[0.14em] md:tracking-widest opacity-60 mb-0.5">{t('sources.quality')}</span>
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

              if (HIGH_TRUST_TIERS.has(source.trust_tier)) bgClass = 'bg-emerald-500';
              else if (VERIFIED_TIERS.has(source.trust_tier)) bgClass = 'bg-nyt-accent';

              const height = Math.min(100, Math.max(15, value * 100));

              return (
                <div
                  key={i}
                  className={`w-[3px] md:w-1.5 rounded-none ${bgClass} ${opacity} hover:opacity-100 hover:scale-y-125 transition-all duration-200 cursor-crosshair origin-bottom`}
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
    <div className="broadsheet-sources">
      <header className="editorial-masthead mb-10 md:mb-16 border-t border-foreground pt-4">
        <div className="masthead-top mb-6 md:mb-8">
          <span className="masthead-kicker ui-label-min tracking-[0.12em] text-nyt-accent">{t('sources.reputation')}</span>
        </div>
        <div className="masthead-main mb-8 md:mb-12">
          <h1 className="masthead-title font-serif text-4xl md:text-6xl font-black leading-[0.92] tracking-tighter">
            {t('sources.title').split(' ')[0]} <span className="text-nyt-accent italic font-light">{t('sources.title').split(' ')[1] || ''}</span>
          </h1>
          <p className="mt-4 md:mt-6 font-serif text-lg md:text-xl italic text-muted-foreground leading-snug max-w-2xl">
            {t('sources.desc')}
          </p>
        </div>

        <div className="masthead-controls sticky top-[var(--header-height)] z-30 bg-background/80 backdrop-blur-xl border-y border-border py-3 md:py-4 flex flex-col md:flex-row justify-between items-center gap-3 md:gap-[var(--grid-gap)]">
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

          <div className="filter-group flex w-full md:w-auto p-1 bg-secondary/30 rounded-none border border-border shadow-sm">
            {[
              { id: 'all', label: t('sources.all') },
              { id: 'high', label: t('sources.high_trust') },
              { id: 'verified', label: t('sources.verified') }
            ].map(t_tier => (
              <button
                key={t_tier.id}
                onClick={() => setFilterTier(t_tier.id)}
                className={`flex-1 md:flex-none px-3 md:px-4 py-2 rounded-none ui-label-min transition-all ${
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

      {/* NEW: Media Pluralism & Bias Spectrum Dashboard */}
      {!loading && !error && domesticGraphSources.length > 0 && (
        <section className="media-spectrum-dashboard mb-16 border border-border/80 bg-secondary/5 dark:bg-secondary/5 rounded-none p-5 md:p-8 backdrop-blur-xl relative overflow-hidden">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/60 pb-5 mb-6">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Compass className="text-nyt-accent shrink-0" size={20} />
                <h2 className="font-serif font-black text-xl md:text-2xl text-foreground leading-none">{t('sources.spectrum_title')}</h2>
              </div>
              <p className="font-serif text-sm italic text-muted-foreground/90">{t('sources.spectrum_subtitle')}</p>
            </div>
            
            {/* Interactive Graph Finder */}
            <div className="relative w-full md:w-72 shrink-0">
              <input
                type="text"
                value={graphSearch}
                onChange={(e) => setGraphSearch(e.target.value)}
                placeholder={t('sources.graph_search_placeholder')}
                className="w-full bg-background border border-border rounded-none py-1.5 pl-3 pr-8 text-xs font-sans placeholder:italic placeholder:opacity-50 focus:border-nyt-accent focus:ring-1 focus:ring-nyt-accent/30 outline-none transition-all"
              />
              <div className="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none opacity-40">
                <Search size={14} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* The Plot Area */}
            <div className="lg:col-span-3">
              <div className="relative w-full h-[400px] md:h-[480px] bg-background/40 border border-border/60 rounded-none overflow-hidden cursor-crosshair select-none shadow-inner">
                
                {/* Horizontal axis grid line */}
                <div className="absolute top-1/2 left-0 right-0 h-[1.5px] bg-foreground/20 dark:bg-foreground/15 border-t border-dashed border-foreground/10 pointer-events-none" />
                {/* Vertical axis grid line */}
                <div className="absolute left-1/2 top-0 bottom-0 w-[1.5px] bg-foreground/20 dark:bg-foreground/15 border-l border-dashed border-foreground/10 pointer-events-none" />
                
                {/* Dynamic radial gradient glow at intersection */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 rounded-full bg-[radial-gradient(circle,rgba(235,94,40,0.12)_0%,transparent_70%)] blur-xl pointer-events-none opacity-70 dark:opacity-50" />

                {/* Visual coordinate grid lines */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-[0.06] dark:opacity-[0.1]">
                  <circle cx="50%" cy="50%" r="18%" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
                  <circle cx="50%" cy="50%" r="35%" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
                  <circle cx="50%" cy="50%" r="48%" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
                </svg>

                {/* Quadrant Text Overlays (Styled Broadsheet Badges) */}
                <div className="absolute top-3 left-4 ui-label-min font-black uppercase tracking-[0.14em] text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_independent_consensus')}
                </div>
                <div className="absolute bottom-3 left-4 ui-label-min font-black uppercase tracking-[0.14em] text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_investigative_exclusives')}
                </div>
                <div className="absolute top-3 right-4 ui-label-min font-black uppercase tracking-[0.14em] text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_sensational_consensus')}
                </div>
                <div className="absolute bottom-3 right-4 ui-label-min font-black uppercase tracking-[0.14em] text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_tabloid_exclusives')}
                </div>

                {/* Core Axis Anchors with Directional Indicators */}
                <div className="absolute top-2.5 left-1/2 -translate-x-1/2 ui-label-min tracking-[0.18em] text-muted-foreground/45 pointer-events-none flex items-center gap-1">
                  ▲ {t('sources.label_consensus')}
                </div>
                <div className="absolute bottom-2.5 left-1/2 -translate-x-1/2 ui-label-min tracking-[0.18em] text-muted-foreground/45 pointer-events-none flex items-center gap-1">
                  ▼ {t('sources.label_exclusives')}
                </div>
                <div className="absolute top-1/2 -translate-y-1/2 left-3.5 ui-label-min tracking-[0.18em] text-muted-foreground/45 pointer-events-none vertical-text flex items-center gap-1">
                  ◀ {t('sources.label_independence')}
                </div>
                <div className="absolute top-1/2 -translate-y-1/2 right-3.5 ui-label-min tracking-[0.18em] text-muted-foreground/45 pointer-events-none vertical-text flex items-center gap-1">
                  ▶ {t('sources.label_tabloids')}
                </div>

                {/* Center marker */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full border border-nyt-accent/25 bg-background/50 backdrop-blur-[3px] pointer-events-none flex items-center justify-center shadow-sm">
                  <span className="text-[7px] font-sans font-black tracking-widest text-nyt-accent/80">CENTER</span>
                </div>

                {/* Rendering reactive nodes */}
                {domesticGraphSources.map((s) => {
                  const coords = getCoordinates(s, lang);
                  const isSelected = selectedSource?.source === s.source;
                  const isHovered = hoveredSource?.source === s.source;
                  const matched = isMatchedByFilter(s);
                  
                  // Pulse animation indicator if search-highlighted
                  const isSearched = graphSearch.trim() !== '' && s.source.toLowerCase().includes(graphSearch.toLowerCase());
                  
                  // Node sizes relative to recent volume activity
                  const nodeSize = 8 + Math.min(14, Math.sqrt(s.recent_volume || 0) * 1.6);
                  
                  // Color codes (High-end glossy bead border styling)
                  let colorClass = 'bg-muted-foreground/70 dark:bg-muted-foreground/50 border border-background dark:border-background/60 shadow-[0_0_8px_rgba(156,163,175,0.3)]';
                  if (HIGH_TRUST_TIERS.has(s.trust_tier)) {
                    colorClass = 'bg-emerald-500 border border-background dark:border-background/60 shadow-[0_0_12px_rgba(16,185,129,0.7)]';
                  } else if (VERIFIED_TIERS.has(s.trust_tier)) {
                    colorClass = 'bg-nyt-accent border border-background dark:border-background/60 shadow-[0_0_12px_rgba(235,94,40,0.7)]';
                  }
                  
                  // Opacity and scale adjustments based on current filters
                  const activeOpacity = matched ? 'opacity-100 scale-100 z-20' : 'opacity-15 scale-75 hover:opacity-40 z-10';
                  
                  return (
                    <div
                      key={s.source}
                      className={`absolute transform -translate-x-1/2 -translate-y-1/2 rounded-full cursor-pointer transition-all duration-300 node-interactive ${colorClass} ${activeOpacity} ${isSelected ? 'ring-4 ring-nyt-accent/40 scale-125 z-30' : 'hover:scale-130'}`}
                      style={{
                        left: `${coords.pctX}%`,
                        top: `${coords.pctY}%`,
                        width: `${nodeSize}px`,
                        height: `${nodeSize}px`
                      }}
                      onClick={() => {
                        setSelectedSource(s);
                        scrollToSource(s.source);
                      }}
                      onMouseEnter={() => setHoveredSource(s)}
                      onMouseLeave={() => setHoveredSource(null)}
                    >
                      {/* Search radar pulse */}
                      {isSearched && (
                        <div className="absolute -inset-3 rounded-full border-2 border-nyt-accent animate-ping pointer-events-none" />
                      )}
                      {/* Small text label for highly prominent media */}
                      {(s.recent_volume > 15 || isSelected || isSearched || isHovered) && matched && (
                        <span className={`absolute top-full left-1/2 -translate-x-1/2 mt-1.5 px-1 py-0.5 rounded-none bg-background/90 text-foreground font-sans ui-label-min tracking-tight border border-border/40 whitespace-nowrap shadow-sm pointer-events-none ${isHovered || isSelected ? 'opacity-100 z-50 scale-105 border-nyt-accent/50' : 'opacity-55'}`}>
                          {s.source}
                        </span>
                      )}
                    </div>
                  );
                })}

                {/* FLOATING HOVER CARD */}
                {hoveredSource && (() => {
                  const coords = getCoordinates(hoveredSource, lang);
                  const showLeft = coords.pctX > 50;
                  const showTop = coords.pctY > 50;
                  const reliability = ((hoveredSource.corroboration_rate * 0.7) + ((hoveredSource.speed_first_count > 0 ? 0.3 : 0))).toFixed(2);
                  
                  return (
                    <div
                      className="absolute z-50 p-4 w-60 border border-border bg-background/95 dark:bg-background/95 shadow-2xl rounded-none transition-all duration-200 pointer-events-none text-left"
                      style={{
                        left: showLeft ? `calc(${coords.pctX}% - 260px)` : `calc(${coords.pctX}% + 20px)`,
                        top: showTop ? `calc(${coords.pctY}% - 120px)` : `calc(${coords.pctY}% + 10px)`,
                      }}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <h4 className="font-serif font-black text-sm text-foreground leading-tight">{hoveredSource.source}</h4>
                        <span className="px-1.5 py-0.5 bg-foreground text-background ui-label-min rounded-none">
                          {hoveredSource.country || defaultCountry}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground italic mb-3 line-clamp-1">{hoveredSource.tendency}</p>
                      
                      <div className="grid grid-cols-2 gap-2 ui-label-min border-t border-border/60 pt-2.5">
                        <div className="flex flex-col">
                          <span className="font-black uppercase tracking-wider text-muted-foreground/60">{t('sources.hover_quality')}</span>
                          <strong className="text-xs font-black text-nyt-accent">{reliability}</strong>
                        </div>
                        <div className="flex flex-col">
                          <span className="font-black uppercase tracking-wider text-muted-foreground/60">{t('sources.hover_consensus')}</span>
                          <strong className="text-xs font-black text-foreground">{formatPercent(hoveredSource.corroboration_rate)}</strong>
                        </div>
                        <div className="flex flex-col mt-1">
                          <span className="font-black uppercase tracking-wider text-muted-foreground/60">{t('sources.hover_volume_24h')}</span>
                          <strong className="text-xs font-black text-foreground">{hoveredSource.recent_volume}</strong>
                        </div>
                        <div className="flex flex-col mt-1">
                          <span className="font-black uppercase tracking-wider text-muted-foreground/60">{t('sources.hover_first_leader')}</span>
                          <strong className="text-xs font-black text-foreground">+{hoveredSource.speed_first_count}</strong>
                        </div>
                      </div>
                      
                      <div className="mt-3.5 ui-label-min text-nyt-accent flex items-center gap-1">
                        <ShieldCheck size={10} />
                        {hoveredSource.trust_tier}
                      </div>
                    </div>
                  );
                })()}

              </div>
              <div className="flex items-center gap-1.5 mt-3 justify-end ui-label-min font-bold text-muted-foreground/75">
                <HelpCircle size={12} />
                <span>{t('sources.graph_hover_hint')}</span>
              </div>
            </div>

            {/* Sidebar Quadrant Legend */}
            <div className="lg:col-span-1 flex flex-col justify-between gap-4 p-4 bg-background/50 border border-border/60 rounded-none">
              <div>
                <h4 className="ui-label border-b border-border/50 pb-2 mb-3 text-foreground">{t('sources.graph_legend')}</h4>
                <div className="space-y-4 text-xs">
                  <div>
                    <span className="inline-block px-1.5 py-0.5 rounded-none bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ui-label-min mb-1">{t('sources.high_trust')}</span>
                    <p className="text-[11px] text-muted-foreground leading-snug">
                      {t('sources.legend_high_trust_desc')}
                    </p>
                  </div>
                  <div>
                    <span className="inline-block px-1.5 py-0.5 rounded-none bg-nyt-accent/10 text-nyt-accent ui-label-min mb-1">{t('sources.verified')}</span>
                    <p className="text-[11px] text-muted-foreground leading-snug">
                      {t('sources.legend_verified_desc')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="border-t border-border/40 pt-3">
                <h5 className="ui-label-min text-foreground mb-1">{t('sources.reporting_angles_title')}</h5>
                <p className="text-xs text-muted-foreground/80 leading-relaxed">
                  {t('sources.reporting_angles_desc')}
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="broadsheet-grid">
        <div className="broadsheet-main">
          {loading ? (
            <div className="py-32 text-center opacity-30">
              <Activity size={48} className="animate-spin mx-auto text-nyt-accent" />
            </div>
          ) : error ? (
            <div className="py-24 text-center border-2 border-dashed border-border rounded-none">
              <h2 className="font-serif text-2xl italic text-muted-foreground">{error}</h2>
            </div>
          ) : (
            <div className="space-y-14 md:space-y-24">
              <section>
                <h2 className="section-heading mb-6 md:mb-10 pb-2 md:pb-3 border-b-4 border-foreground">
                  {lang === 'mk' ? t('sources.mk_media') : t('sources.sr_media')}
                </h2>
                <div className="flex flex-col">
                  {mkSources.map(renderSourceRow)}
                </div>
              </section>
              <section>
                <h2 className="section-heading mb-6 md:mb-10 pb-2 md:pb-3 border-b-4 border-foreground">
                  {t('sources.intl_signals')}
                </h2>
                <div className="flex flex-col">
                  {intSources.map(renderSourceRow)}
                </div>
              </section>
            </div>
          )}
        </div>

        <aside className="broadsheet-rail pl-0 md:pl-4">
          <section className="rail-module mb-8 md:mb-12 p-4 md:p-8 bg-nyt-accent/5 border border-nyt-accent/10 rounded-none">
            <span className="block font-sans ui-label-min font-black uppercase tracking-[0.16em] md:tracking-[0.2em] text-nyt-accent mb-3 md:mb-4">{t('briefing.system_balance')}</span>
            <h3 className="section-heading mb-4 leading-tight tracking-tight">{t('sources.qi_title')}</h3>
            <p className="font-nyt-body text-sm leading-relaxed text-muted-foreground">
              {t('sources.qi_desc')}
            </p>
          </section>

          <details className="izvori-rail-context">
            <summary className="izvori-rail-context-summary">
              <span>{lang === 'mk' ? 'Контекст и методологија' : 'Kontekst i metodologija'}</span>
              <span className="izvori-rail-context-hint ui-label-min text-muted-foreground">{lang === 'mk' ? 'ОТВОРИ' : 'OTVORI'}</span>
            </summary>
            <div className="izvori-rail-context-body">
              <section className="rail-module mb-8 md:mb-12">
                <h3 className="ui-label text-foreground mb-4 md:mb-6 pb-2 border-b-2 border-foreground">{t('sources.fastest_today')}</h3>
                <div className="flex flex-col gap-1">
                  {fastMovers.map(s => (
                    <div key={s.source} className="flex items-center justify-between py-2 border-b border-border/40 hover:bg-secondary/10 px-1 transition-all gap-2">
                      <span className="font-serif font-bold text-sm md:text-base">{s.source}</span>
                      <span className="ui-label text-nyt-accent bg-nyt-accent/10 px-2 py-0.5 rounded-none">+{s.speed_first_count}</span>
                    </div>
                  ))}
                </div>
              </section>

              <div className="rail-methodology-module p-4 md:p-6 bg-secondary/10 border border-border/40 rounded-none">
                <h4 className="ui-label-min border-b border-border pb-3 mb-4">{t('sources.methodology')}</h4>
                <ul className="space-y-3 md:space-y-4">
                  <li className="flex flex-col gap-1">
                    <span className="ui-label-min text-foreground">{t('sources.trust')}</span>
                    <span className="text-xs text-muted-foreground leading-snug">
                      {t('sources.trust_desc')}
                    </span>
                  </li>
                  <li className="flex flex-col gap-1">
                    <span className="ui-label-min text-foreground">{t('sources.leadership')}</span>
                    <span className="text-xs text-muted-foreground leading-snug">
                      {t('sources.leadership_desc')}
                    </span>
                  </li>
                  <li className="flex flex-col gap-1">
                    <span className="ui-label-min text-foreground">{t('sources.confirmation')}</span>
                    <span className="text-xs text-muted-foreground leading-snug">
                      {t('sources.confirmation_desc')}
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </details>
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
          .broadsheet-grid { grid-template-columns: 3fr 1fr; }
          .broadsheet-rail { align-self: start; position: sticky; top: calc(var(--header-height) + 1.5rem); }
        }

        .izvori-rail-context {
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--secondary) 15%, var(--background));
        }

        .izvori-rail-context-summary {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 0.9rem;
          cursor: pointer;
          list-style: none;
          font-family: var(--font-ui);
          font-size: var(--text-ui-kicker);
          font-weight: 800;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        .izvori-rail-context-summary::-webkit-details-marker { display: none; }

        .izvori-rail-context-hint::after { content: ' +'; color: var(--nyt-accent); }
        .izvori-rail-context[open] .izvori-rail-context-hint::after { content: ' −'; }

        .izvori-rail-context-body {
          padding: 0.85rem 0.9rem 1rem;
          border-top: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
        }

        @media (min-width: 1024px) {
          .izvori-rail-context { border: none; background: transparent; }
          .izvori-rail-context-summary { display: none; }
          .izvori-rail-context-body { padding: 0; border-top: none; }
        }

        .vertical-text {
          writing-mode: vertical-lr;
          transform: rotate(180deg);
        }

        @keyframes highlightPulse {
          0% { background-color: rgba(235, 94, 40, 0.25); border-left-color: var(--nyt-accent); }
          50% { background-color: rgba(235, 94, 40, 0.1); }
          100% { background-color: transparent; }
        }
        .highlight-pulse {
          animation: highlightPulse 2.5s cubic-bezier(0.25, 1, 0.5, 1) forwards;
          border-left: 4px solid var(--nyt-accent);
          padding-left: 1rem;
        }

        .node-interactive {
          transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.3s ease, filter 0.3s ease, box-shadow 0.3s ease;
        }
        .node-interactive:hover {
          filter: brightness(1.1);
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
