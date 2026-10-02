import { homePath, localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, ShieldCheck, Zap, Activity, ChevronRight, Globe, Compass, HelpCircle, X, ExternalLink } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { sources as sourcesNamespace } from '../i18n/namespaces/sources';
import PresekAdRailSlot from './PresekAdRailSlot';
import type { ui } from '../i18n/ui';

// Inlined API base so this island does not import the shared apiBase chunk.
// That chunk (/ _astro/apiBase.*.js) was intermittently 404ing on the public
// edge, which broke the island's module graph and left /izvori stuck on its
// loading spinner. Keeping the value local makes the island self-contained.
function apiBaseUrl(): string {
  const fromEnv = import.meta.env?.PUBLIC_API_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined') return '/api';
  return (typeof process !== 'undefined' && process.env.INTERNAL_API_URL) || 'http://127.0.0.1:5001/api';
}

interface SourceRow {
  source: string;
  country: string;
  category: string;
  top_categories: string[];
  credibility: number;
  effective_weight: number;
  trust_tier: string;
  trust_tier_code?: string;
  trend_code?: string;
  tendency_code?: string;
  daily_volume?: number[];
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

// /api/sources returns category values in Latin; render them in Macedonian.
const CATEGORY_MK: Record<string, string> = {
  Makedonija: 'Македонија', Svet: 'Свет', Balkan: 'Балкан', Region: 'Регион',
  Politika: 'Политика', Ekonomija: 'Економија', Sport: 'Спорт', Kultura: 'Култура',
  Tehnologija: 'Технологија', Zivot: 'Живот', Zabava: 'Забава', Zdravje: 'Здравје',
};
function localizeCategory(cat: string, lang: string) {
  return lang === 'mk' ? (CATEGORY_MK[cat] || cat) : cat;
}

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

const IzvoriPage: React.FC<{ lang?: keyof typeof ui }> = ({ lang = 'mk' }) => {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTier, setFilterTier] = useState<string>('all');
  const t = useClientTranslations(lang, sourcesNamespace);
  const tRef = useRef(t);
  tRef.current = t;
  const dateLocale = lang === 'mk' ? 'mk-MK' : 'sr-RS';
  const defaultCountry = lang === 'mk' ? 'MK' : 'RS';

  // New interactive graph states
  const [graphSearch, setGraphSearch] = useState('');
  const [hoveredSource, setHoveredSource] = useState<SourceRow | null>(null);
  const [selectedSource, setSelectedSource] = useState<SourceRow | null>(null);

  // Rankings table + source detail drawer
  type SortKey = 'source' | 'recent_volume' | 'speed_first_count' | 'corroboration_rate' | 'lone_lead_rate' | 'effective_weight';
  const [sortKey, setSortKey] = useState<SortKey>('effective_weight');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [drawerSource, setDrawerSource] = useState<SourceRow | null>(null);
  const [drawerStories, setDrawerStories] = useState<any[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const tierLabel = (s: SourceRow) => {
    const code = s.trust_tier_code
      || (HIGH_TRUST_TIERS.has(s.trust_tier) ? 'high' : VERIFIED_TIERS.has(s.trust_tier) ? 'verified' : 'standard');
    return t(`sources.tier_${code}`);
  };
  const trendLabel = (s: SourceRow) => t(`sources.trend_${s.trend_code || 'stable'}`);
  const tendencyLabel = (s: SourceRow) => t(`sources.tendency_${s.tendency_code || 'follower'}`);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const openDrawer = async (source: SourceRow) => {
    setDrawerSource(source);
    setDrawerLoading(true);
    setDrawerStories([]);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('source', source.source);
      window.history.replaceState({}, '', url.toString());
    } catch {}
    try {
      const res = await fetch(`${apiBaseUrl()}/news?source=${encodeURIComponent(source.source)}&lang=${lang}&page_size=8`);
      const data = await res.json();
      const clusters = Array.isArray(data?.clusters) ? data.clusters : (Array.isArray(data) ? data : []);
      setDrawerStories(clusters.slice(0, 8));
    } catch {
      setDrawerStories([]);
    } finally {
      setDrawerLoading(false);
    }
  };

  const closeDrawer = () => {
    setDrawerSource(null);
    setDrawerStories([]);
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete('source');
      window.history.replaceState({}, '', url.toString());
    } catch {}
  };

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${apiBaseUrl()}/sources?t=${Date.now()}`);
        if (!res.ok) {
          setError(tRef.current('sources.connection_error'));
          return;
        }
        const allRes = await res.json();
        setSources(allRes);
      } catch {
        setError(tRef.current('sources.connection_error'));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [lang]);

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

  const rankedSources = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = a[sortKey] as any;
      const bv = b[sortKey] as any;
      const cmp = typeof av === 'string' || typeof bv === 'string'
        ? String(av).localeCompare(String(bv))
        : (Number(av) || 0) - (Number(bv) || 0);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  // Deep link: /izvori?source=NAME opens the drawer for that source.
  useEffect(() => {
    if (loading || !sources.length || drawerSource) return;
    const wanted = new URLSearchParams(window.location.search).get('source');
    if (!wanted) return;
    const match = sources.find((s) => s.source === wanted);
    if (match) void openDrawer(match);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, sources]);

  // Escape closes the drawer.
  useEffect(() => {
    if (!drawerSource) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeDrawer(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawerSource]);

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
    const isSelected = selectedSource?.source === source.source || drawerSource?.source === source.source;
    const rowId = `source-${encodeURIComponent(source.source)}`;
    const daily = Array.isArray(source.daily_volume) && source.daily_volume.length ? source.daily_volume : null;
    const dailyMax = daily ? Math.max(1, ...daily) : 1;

    return (
      <a
        key={source.source}
        id={rowId}
        href={`${localePathForLang('/', lang)}?source=${encodeURIComponent(source.source)}`}
        className={`editorial-source-item group no-underline transition-all duration-300 ${isSelected ? 'border-l-4 border-l-presek-mark pl-4 bg-presek-mark/5' : ''}`}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          void openDrawer(source);
        }}
      >
        <div className="item-main">
          <div className="item-head mb-2">
            <div className={`health-dot ${health}`} title={health === 'active' ? t('sources.health_active') : health === 'stale' ? t('sources.health_stale') : t('sources.health_critical')}></div>
            <h3 className="section-heading group-hover:text-presek-mark transition-colors">{source.source}</h3>
            {(HIGH_TRUST_TIERS.has(source.trust_tier) || source.trust_tier_code === 'high') && (
              <ShieldCheck size={14} className="text-presek-mark" />
            )}
          </div>
          <p className="item-tendency font-nyt-body text-sm text-muted-foreground line-clamp-1 mb-2 md:mb-3">{tendencyLabel(source)}</p>
          <div className="item-meta flex items-center gap-2 md:gap-[var(--grid-gap)]">
            <span className="px-2 py-0.5 bg-foreground text-background ui-status">{source.country || defaultCountry}</span>
            <div className="flex gap-1.5">
              {source.top_categories?.slice(0, 2).map(cat => (
                <span key={cat} className="px-2 py-0.5 border border-border rounded-none ui-status text-muted-foreground/80">{localizeCategory(cat, lang)}</span>
              ))}
            </div>
            <span className="ui-status text-muted-foreground/40 ml-auto flex items-center gap-1.5">
              <Activity size={10} /> {formatLastFetched(source.last_fetched, t('sources.no_signal'), dateLocale)}
            </span>
          </div>
        </div>
        <div className="item-stats flex items-center justify-end gap-3 md:gap-[var(--grid-gap)] ml-auto flex-1 min-w-[200px]">
          <div className="flex gap-3 md:gap-[var(--grid-gap)]">
            <div className="stat-box flex flex-col items-end">
              <span className="ui-kicker text-muted-foreground mb-0.5">{t('sources.news_24h')}</span>
              <strong className="text-base md:text-lg font-black tabular-nums leading-none">{source.recent_volume}</strong>
            </div>
            <div className="stat-box flex flex-col items-end text-presek-mark" title={t('sources.metric_corroboration_tip')}>
              <span className="ui-kicker opacity-60 mb-0.5">{t('sources.metric_corroboration')}</span>
              <strong className="text-base md:text-lg font-black tabular-nums leading-none">{formatPercent(source.corroboration_rate)}</strong>
            </div>
          </div>

          <div className="heatmap-container flex gap-[2px] items-end h-8 shrink-0" title={t('sources.activity_30d')}>
            {daily ? daily.map((v, i) => {
              const ratio = v / dailyMax;
              let opacity = ratio > 0.75 ? 'opacity-100' : ratio > 0.45 ? 'opacity-60' : ratio > 0.15 ? 'opacity-40' : 'opacity-10';
              let bgClass = 'bg-foreground';
              if (HIGH_TRUST_TIERS.has(source.trust_tier) || source.trust_tier_code === 'high') bgClass = 'bg-emerald-500';
              else if (VERIFIED_TIERS.has(source.trust_tier) || source.trust_tier_code === 'verified') bgClass = 'bg-presek-mark';
              const height = Math.min(100, Math.max(8, ratio * 100));
              return (
                <div
                  key={i}
                  className={`w-[3px] md:w-1.5 rounded-none ${bgClass} ${opacity} hover:opacity-100 transition-all duration-200 origin-bottom`}
                  style={{ height: `${height}%` }}
                  title={`${v} · ${daily.length - 1 - i}d`}
                />
              );
            }) : (
              <span className="ui-label-min text-muted-foreground/40">{t('sources.no_signal')}</span>
            )}
          </div>
        </div>
      </a>
    );
  };

  return (
    <div className="broadsheet-sources">
      <header className="editorial-masthead mb-10 md:mb-16 border-t border-foreground pt-4">
        <div className="masthead-top mb-6 md:mb-8">
          <span className="masthead-kicker ui-kicker ui-kicker--accent">{t('sources.page_kicker')}</span>
        </div>
        <div className="masthead-main mb-8 md:mb-12">
          <h1 className="masthead-title font-serif text-4xl md:text-6xl font-black leading-[0.92] tracking-tighter">
            {t('sources.title').split(' ')[0]} <span className="text-presek-mark italic font-light">{t('sources.title').split(' ')[1] || ''}</span>
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
              className="w-full bg-secondary/20 border-b-2 border-border py-2 pl-2 pr-10 font-serif font-bold text-base md:text-lg outline-none focus:border-presek-mark placeholder:italic placeholder:font-normal placeholder:opacity-40 transition-all"
            />
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none opacity-40">
              <Search size={18} />
            </div>
          </div>

          <div className="filter-group flex w-full md:w-auto p-1 bg-secondary/30 rounded-none border border-border">
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
                    ? 'bg-presek-mark text-white'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t_tier.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {!loading && !error && domesticGraphSources.length > 0 && (
        <details className="sources-analytics-details mb-16">
          <summary className="sources-analytics-summary">
            <span className="sources-analytics-title">{t('sources.analytics_panel')}</span>
            <span className="sources-analytics-hint">{t('sources.analytics_hint')}</span>
          </summary>
          <div className="sources-analytics-body">
        <section className="media-spectrum-dashboard border border-border/80 bg-secondary/5 dark:bg-secondary/5 rounded-none p-5 md:p-8 backdrop-blur-xl relative overflow-hidden">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/60 pb-5 mb-6">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Compass className="text-presek-mark shrink-0" size={20} />
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
                className="w-full bg-background border border-border rounded-none py-1.5 pl-3 pr-8 text-xs font-sans placeholder:italic placeholder:opacity-50 focus:border-presek-mark focus:ring-1 focus:ring-presek-mark/30 outline-none transition-all"
              />
              <div className="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none opacity-40">
                <Search size={14} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* The Plot Area */}
            <div className="lg:col-span-3">
              <div className="relative w-full h-[400px] md:h-[480px] bg-background/40 border border-border/60 rounded-none overflow-hidden cursor-crosshair select-none">
                
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
                <div className="absolute top-3 left-4 ui-kicker text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_independent_consensus')}
                </div>
                <div className="absolute bottom-3 left-4 ui-kicker text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_investigative_exclusives')}
                </div>
                <div className="absolute top-3 right-4 ui-kicker text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_sensational_consensus')}
                </div>
                <div className="absolute bottom-3 right-4 ui-kicker text-muted-foreground/35 bg-secondary/20 dark:bg-secondary/10 px-2 py-0.5 border border-border/10 rounded-none pointer-events-none">
                  {t('sources.quadrant_tabloid_exclusives')}
                </div>

                {/* Core Axis Anchors with Directional Indicators */}
                <div className="absolute top-2.5 left-1/2 -translate-x-1/2 ui-kicker text-muted-foreground/45 pointer-events-none flex items-center gap-1">
                  ▲ {t('sources.label_consensus')}
                </div>
                <div className="absolute bottom-2.5 left-1/2 -translate-x-1/2 ui-kicker text-muted-foreground/45 pointer-events-none flex items-center gap-1">
                  ▼ {t('sources.label_exclusives')}
                </div>
                <div className="absolute top-1/2 -translate-y-1/2 left-3.5 ui-kicker text-muted-foreground/45 pointer-events-none vertical-text flex items-center gap-1">
                  ◀ {t('sources.label_independence')}
                </div>
                <div className="absolute top-1/2 -translate-y-1/2 right-3.5 ui-kicker text-muted-foreground/45 pointer-events-none vertical-text flex items-center gap-1">
                  ▶ {t('sources.label_tabloids')}
                </div>

                {/* Center marker */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full border border-presek-mark/25 bg-background/50 backdrop-blur-[3px] pointer-events-none flex items-center justify-center shadow-sm">
                  <span className="text-[7px] font-sans font-black tracking-widest text-presek-mark/80">CENTER</span>
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
                    colorClass = 'bg-presek-mark border border-background dark:border-background/60 shadow-[0_0_12px_rgba(235,94,40,0.7)]';
                  }
                  
                  // Opacity and scale adjustments based on current filters
                  const activeOpacity = matched ? 'opacity-100 scale-100 z-20' : 'opacity-15 scale-75 hover:opacity-40 z-10';
                  
                  return (
                    <div
                      key={s.source}
                      className={`absolute transform -translate-x-1/2 -translate-y-1/2 rounded-full cursor-pointer transition-all duration-300 node-interactive ${colorClass} ${activeOpacity} ${isSelected ? 'ring-4 ring-presek-mark/40 scale-125 z-30' : 'hover:scale-130'}`}
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
                        <div className="absolute -inset-3 rounded-full border-2 border-presek-mark animate-ping pointer-events-none" />
                      )}
                      {/* Small text label for highly prominent media */}
                      {(s.recent_volume > 15 || isSelected || isSearched || isHovered) && matched && (
                        <span className={`absolute top-full left-1/2 -translate-x-1/2 mt-1.5 px-1 py-0.5 rounded-none bg-background/90 text-foreground font-sans ui-label-min tracking-tight border border-border/40 whitespace-nowrap shadow-sm pointer-events-none ${isHovered || isSelected ? 'opacity-100 z-50 scale-105 border-presek-mark/50' : 'opacity-55'}`}>
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
                  
                  return (
                    <div
                      className="absolute z-50 p-4 w-60 border border-border bg-background/95 dark:bg-background/95 shadow-none rounded-none transition-all duration-200 pointer-events-none text-left"
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
                      <p className="text-[11px] text-muted-foreground italic mb-3 line-clamp-1">{tendencyLabel(hoveredSource)}</p>
                      
                      <div className="grid grid-cols-2 gap-2 ui-label-min border-t border-border/60 pt-2.5">
                        <div className="flex flex-col">
                          <span className="ui-kicker text-muted-foreground/60">{t('sources.metric_corroboration')}</span>
                          <strong className="text-xs font-black text-presek-mark">{formatPercent(hoveredSource.corroboration_rate)}</strong>
                        </div>
                        <div className="flex flex-col">
                          <span className="ui-kicker text-muted-foreground/60">{t('sources.hover_consensus')}</span>
                          <strong className="text-xs font-black text-foreground">{formatPercent(hoveredSource.corroboration_rate)}</strong>
                        </div>
                        <div className="flex flex-col mt-1">
                          <span className="ui-kicker text-muted-foreground/60">{t('sources.hover_volume_24h')}</span>
                          <strong className="text-xs font-black text-foreground">{hoveredSource.recent_volume}</strong>
                        </div>
                        <div className="flex flex-col mt-1">
                          <span className="ui-kicker text-muted-foreground/60">{t('sources.hover_first_leader')}</span>
                          <strong className="text-xs font-black text-foreground">+{hoveredSource.speed_first_count}</strong>
                        </div>
                      </div>
                      
                      <div className="mt-3.5 ui-label-min text-presek-mark flex items-center gap-1">
                        <ShieldCheck size={10} />
                        {tierLabel(hoveredSource)}
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
                <h4 className="ui-kicker border-b border-border/50 pb-2 mb-3 text-foreground">{t('sources.graph_legend')}</h4>
                <div className="space-y-4 text-xs">
                  <div>
                    <span className="inline-block px-1.5 py-0.5 rounded-none bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ui-label-min mb-1">{t('sources.high_trust')}</span>
                    <p className="text-[11px] text-muted-foreground leading-snug">
                      {t('sources.legend_high_trust_desc')}
                    </p>
                  </div>
                  <div>
                    <span className="inline-block px-1.5 py-0.5 rounded-none bg-presek-mark/10 text-presek-mark ui-label-min mb-1">{t('sources.verified')}</span>
                    <p className="text-[11px] text-muted-foreground leading-snug">
                      {t('sources.legend_verified_desc')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="border-t border-border/40 pt-3">
                <h5 className="ui-kicker text-foreground mb-1">{t('sources.reporting_angles_title')}</h5>
                <p className="text-xs text-muted-foreground/80 leading-relaxed">
                  {t('sources.reporting_angles_desc')}
                </p>
              </div>
            </div>
          </div>
        </section>
          </div>
        </details>
      )}

      <div className="broadsheet-grid">
        <div className="broadsheet-main">
          {loading ? (
            <div className="py-32 text-center opacity-30">
              <Activity size={48} className="animate-spin mx-auto text-presek-mark" />
            </div>
          ) : error ? (
            <div className="py-24 text-center border-2 border-dashed border-border rounded-none">
              <h2 className="font-serif text-2xl italic text-muted-foreground">{error}</h2>
            </div>
          ) : (
            <div className="space-y-10 md:space-y-14">
              <section className="sources-rankings">
                <h2 className="section-heading mb-2 pb-2 md:pb-3 border-b-4 border-foreground">{t('sources.rankings_title')}</h2>
                <p className="text-sm text-muted-foreground mb-4 md:mb-6">{t('sources.rankings_desc')}</p>
                <div className="sources-rank-scroll overflow-x-auto">
                  <table className="sources-rank-table w-full text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-foreground text-left ui-kicker">
                        {([
                          ['source', t('sources.col_source')],
                          ['recent_volume', t('sources.col_volume')],
                          ['speed_first_count', t('sources.col_scoops')],
                          ['corroboration_rate', t('sources.col_corroboration')],
                          ['lone_lead_rate', t('sources.col_lone')],
                          ['effective_weight', t('sources.col_weight')],
                        ] as [SortKey, string][]).map(([key, label]) => (
                          <th key={key} className="py-2 pr-3 whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => toggleSort(key)}
                              className="inline-flex items-center gap-1 hover:text-presek-mark transition-colors"
                            >
                              {label}
                              <span aria-hidden="true" className="opacity-70">{sortKey === key ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}</span>
                            </button>
                          </th>
                        ))}
                        <th className="py-2 whitespace-nowrap">{t('sources.col_trend')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankedSources.map((s) => (
                        <tr
                          key={s.source}
                          className="border-b border-border/40 hover:bg-secondary/10 cursor-pointer"
                          onClick={() => void openDrawer(s)}
                        >
                          <td className="py-2 pr-3 font-serif font-bold">{s.source}</td>
                          <td className="py-2 pr-3 tabular-nums">{s.recent_volume}</td>
                          <td className="py-2 pr-3 tabular-nums">+{s.speed_first_count}</td>
                          <td className="py-2 pr-3 tabular-nums">{formatPercent(s.corroboration_rate)}</td>
                          <td className="py-2 pr-3 tabular-nums">{formatPercent(s.lone_lead_rate)}</td>
                          <td className="py-2 pr-3 tabular-nums">{s.effective_weight}</td>
                          <td className={`py-2 whitespace-nowrap ${s.trend_code === 'up' ? 'text-emerald-600' : s.trend_code === 'down' ? 'text-red-500' : 'text-muted-foreground'}`}>{trendLabel(s)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details className="mt-4">
                  <summary className="cursor-pointer ui-kicker text-presek-mark">{t('sources.how_we_score')}</summary>
                  <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-3xl">{t('sources.how_we_score_body')}</p>
                </details>
              </section>
              <section>
                <h2 className="section-heading mb-3 md:mb-5 pb-2 md:pb-3 border-b-4 border-foreground">
                  {lang === 'mk' ? t('sources.mk_media') : t('sources.sr_media')}
                </h2>
                <div className="sources-compact-list">
                  {mkSources.map(renderSourceRow)}
                </div>
              </section>
              <section>
                <h2 className="section-heading mb-3 md:mb-5 pb-2 md:pb-3 border-b-4 border-foreground">
                  {t('sources.intl_signals')}
                </h2>
                <div className="sources-compact-list">
                  {intSources.map(renderSourceRow)}
                </div>
              </section>
            </div>
          )}
        </div>

        <aside className="broadsheet-rail pl-0 md:pl-4">
          <PresekAdRailSlot lang={lang} />
          <section className="rail-module mb-8 md:mb-12 p-4 md:p-8 bg-presek-mark/5 border border-presek-mark/10 rounded-none">
            <span className="block ui-kicker ui-kicker--accent mb-3 md:mb-4">{t('sources.system_balance')}</span>
            <h3 className="section-heading mb-4 leading-tight tracking-tight">{t('sources.qi_title')}</h3>
            <p className="font-nyt-body text-sm leading-relaxed text-muted-foreground">
              {t('sources.qi_desc')}
            </p>
          </section>

          <details className="izvori-rail-context">
            <summary className="izvori-rail-context-summary">
              <span>{t('sources.rail_context_title')}</span>
              <span className="izvori-rail-context-hint ui-kicker text-muted-foreground">{t('sources.rail_context_open')}</span>
            </summary>
            <div className="izvori-rail-context-body">
              <section className="rail-module mb-8 md:mb-12">
                <h3 className="ui-kicker text-foreground mb-4 md:mb-6 pb-2 border-b-2 border-foreground">{t('sources.fastest_today')}</h3>
                <div className="flex flex-col gap-1">
                  {fastMovers.map(s => (
                    <div key={s.source} className="flex items-center justify-between py-2 border-b border-border/40 hover:bg-secondary/10 px-1 transition-all gap-2">
                      <span className="font-serif font-bold text-sm md:text-base">{s.source}</span>
                      <span className="ui-label text-presek-mark bg-presek-mark/10 px-2 py-0.5 rounded-none">+{s.speed_first_count}</span>
                    </div>
                  ))}
                </div>
              </section>

              <div className="rail-methodology-module p-4 md:p-6 bg-secondary/10 border border-border/40 rounded-none">
                <h4 className="ui-kicker border-b border-border pb-3 mb-4">{t('sources.methodology')}</h4>
                <ul className="space-y-3 md:space-y-4">
                  <li className="flex flex-col gap-1">
                    <span className="ui-kicker text-foreground">{t('sources.trust')}</span>
                    <span className="text-xs text-muted-foreground leading-snug">
                      {t('sources.trust_desc')}
                    </span>
                  </li>
                  <li className="flex flex-col gap-1">
                    <span className="ui-kicker text-foreground">{t('sources.leadership')}</span>
                    <span className="text-xs text-muted-foreground leading-snug">
                      {t('sources.leadership_desc')}
                    </span>
                  </li>
                  <li className="flex flex-col gap-1">
                    <span className="ui-kicker text-foreground">{t('sources.confirmation')}</span>
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

      {drawerSource && (
        <div className="fixed inset-0 z-[9000] flex justify-end" role="dialog" aria-modal="true" aria-label={drawerSource.source}>
          <div className="absolute inset-0 bg-foreground/30 backdrop-blur-sm" onClick={closeDrawer} />
          <aside className="relative h-full w-full max-w-md bg-background border-l border-border overflow-y-auto p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-3 mb-5">
              <div className="min-w-0">
                <h3 className="font-serif font-black text-2xl leading-tight truncate">{drawerSource.source}</h3>
                <p className="text-sm text-muted-foreground italic mt-1">{tierLabel(drawerSource)} · {trendLabel(drawerSource)}</p>
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                aria-label={t('sources.detail_close')}
                className="p-1.5 border border-border hover:bg-secondary transition-colors shrink-0"
              >
                <X size={16} />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.news_24h')}</div>
                <strong className="text-xl font-black tabular-nums">{drawerSource.recent_volume}</strong>
              </div>
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.col_scoops')}</div>
                <strong className="text-xl font-black tabular-nums">+{drawerSource.speed_first_count}</strong>
              </div>
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.metric_corroboration')}</div>
                <strong className="text-xl font-black tabular-nums">{formatPercent(drawerSource.corroboration_rate)}</strong>
              </div>
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.col_lone')}</div>
                <strong className="text-xl font-black tabular-nums">{formatPercent(drawerSource.lone_lead_rate)}</strong>
              </div>
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.col_weight')}</div>
                <strong className="text-xl font-black tabular-nums">{drawerSource.effective_weight}</strong>
              </div>
              <div className="border border-border p-3">
                <div className="ui-kicker text-muted-foreground mb-1">{t('sources.col_source')} · 30д</div>
                <strong className="text-xl font-black tabular-nums">{drawerSource.lead_count_30d}</strong>
              </div>
            </div>

            <a
              href={`${localePathForLang('/archive', lang)}?source=${encodeURIComponent(drawerSource.source)}`}
              className="inline-flex items-center gap-1.5 text-sm font-bold text-presek-mark mb-6 no-underline hover:underline"
            >
              {t('sources.detail_all')} <ExternalLink size={13} />
            </a>

            <h4 className="ui-kicker border-b border-border pb-2 mb-3">{t('sources.detail_recent')}</h4>
            {drawerLoading ? (
              <p className="text-sm text-muted-foreground">{t('sources.detail_loading')}</p>
            ) : drawerStories.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('sources.detail_none')}</p>
            ) : (
              <ul className="space-y-3">
                {drawerStories.map((c: any, i: number) => {
                  const id = c?.cluster_id || c?.id;
                  const title = c?.synthetic_headline || c?.title || (Array.isArray(c?.articles) ? c.articles[0]?.title : '') || '';
                  if (!id || !title) return null;
                  return (
                    <li key={`${id}-${i}`} className="border-b border-border/40 pb-3">
                      <a
                        href={localePathForLang(`/cluster/${id}`, lang)}
                        className="font-serif font-bold text-[15px] leading-snug no-underline hover:text-presek-mark"
                      >
                        {title}
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>
        </div>
      )}

      <style>{`
        .editorial-source-item { display: flex; justify-content: space-between; align-items: center; padding: 1.35rem 0; border-bottom: 1px solid var(--border); transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        .editorial-source-item:hover { background: color-mix(in srgb, var(--background) 96%, var(--presek-mark) 4%); padding-left: 1rem; padding-right: 1rem; margin-left: -1rem; margin-right: -1rem; border-radius: 0px; border-bottom-color: var(--presek-mark); }
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
          font-weight: 700;
          letter-spacing: 0.04em;
        }

        .izvori-rail-context-summary::-webkit-details-marker { display: none; }

        .izvori-rail-context-hint::after { content: ' +'; color: var(--presek-mark); }
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
