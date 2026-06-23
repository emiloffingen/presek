import React, { Suspense, lazy, useState, useEffect, useMemo } from 'react';
import { Activity, Zap, ShieldCheck, Globe, Timer, Loader2, BarChart3, TrendingUp, Users, Info, ChevronRight, Target } from 'lucide-react';
import SourceComparisonIsland from './SourceComparisonIsland';
import PresekAdRailSlot from './PresekAdRailSlot';
import { apiBaseUrl } from '../lib/apiBase';
import { useClientTranslations } from '../i18n/clientTranslations';
import { pulse } from '../i18n/namespaces/pulse';

const PulseLandscapeIsland = lazy(() => import('./PulseLandscapeIsland'));
const PulseHeatmapIsland = lazy(() => import('./pulse/PulseHeatmapIsland'));
const DivergenceGaugeIsland = lazy(() => import('./pulse/DivergenceGaugeIsland'));
const SentimentRadarIsland = lazy(() => import('./pulse/SentimentRadarIsland'));

function PulseChartFallback({ tall = false }: { tall?: boolean }) {
    return (
        <div
            className={`pulse-chart-skeleton ${tall ? 'pulse-chart-skeleton--tall' : ''}`}
            aria-hidden="true"
        />
    );
}

interface PulseRow {
    source: string;
    avg_sentiment: number;
    avg_objectivity: number;
    avg_sensationalism: number;
    cluster_count: number;
    first_report_count: number;
    trust_label?: string;
    effective_weight?: number;
    objectivity_delta?: number;
}

interface PulseClientContainerProps {
    initialGlobalPulse: any;
    initialPulseData: PulseRow[];
    categories: string[];
    ssrFailed?: boolean;
    lang?: string;
}

export default function PulseClientContainer({ initialGlobalPulse, initialPulseData, categories, ssrFailed, lang = 'sr' }: PulseClientContainerProps) {
    const locale = lang === 'mk' ? 'mk' : 'sr';
    const t = useClientTranslations(locale, pulse);

    // URL-aware category state
    const [category, setCategory] = useState<string | null>(() => {
        if (typeof window !== 'undefined') {
            const params = new URLSearchParams(window.location.search);
            return params.get('category');
        }
        return null;
    });

    const [globalPulse, setGlobalPulse] = useState(initialGlobalPulse);
    const [pulseData, setPulseData] = useState<PulseRow[]>(initialPulseData);
    const [loading, setLoading] = useState(false);
    const API_URL = apiBaseUrl();

    useEffect(() => {
        // Sync URL with category
        if (typeof window !== 'undefined') {
            const url = new URL(window.location.href);
            if (category) url.searchParams.set('category', category);
            else url.searchParams.delete('category');
            window.history.replaceState({}, '', url);
        }

        const hasData = !!(globalPulse && pulseData && pulseData.length > 0);
        if (category === null && globalPulse === initialGlobalPulse && hasData && !ssrFailed) return;

        const fetchData = async () => {
            setLoading(true);
            try {
                const catParam = category ? `category=${encodeURIComponent(category)}` : '';
                const langParam = `lang=${lang}`;
                const query = [catParam, langParam].filter(Boolean).join('&');

                const [pulseRes, globalRes] = await Promise.all([
                    fetch(`${API_URL}/intelligence/source-pulse?${query}`),
                    fetch(`${API_URL}/intelligence/global-pulse?${query}`)
                ]);

                if (pulseRes.ok) {
                    const json = await pulseRes.json();
                    setPulseData(json.data || []);
                }
                if (globalRes.ok) {
                    const json = await globalRes.json();
                    setGlobalPulse(json);
                }
            } catch (err) {
                console.error("Pulse fetch error:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [category, lang]);

    const intelligence = globalPulse?.intelligence ?? {};
    const velocityData = globalPulse?.velocity ?? [];
    const topEntities = globalPulse?.top_entities ?? [];
    const topicPulse = globalPulse?.by_topic_sentiment ?? [];
    const pulseLeaders = pulseData.slice(0, 15);

    function getSentimentIcon(score: number) {
        if (score > 0.2) return { icon: <Activity size={14} />, color: 'text-green-600', title: t('pulse.sentiment_positive') };
        if (score < -0.2) return { icon: <Activity size={14} />, color: 'text-nyt-red', title: t('pulse.sentiment_critical') };
        return { icon: <Activity size={14} />, color: 'text-muted-foreground', title: t('pulse.sentiment_neutral') };
    }

    function formatStat(val: number) {
        if (val === 0 || !val) return '–';
        return (val * 100).toFixed(0) + '%';
    }

    function formatCount(val: number | null | undefined) {
        if (!val) return '–';
        return String(Math.round(val)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    }

    function getTypeLabel(type: string) {
        const map: Record<string, string> = {
            PER: 'pulse.entity.per',
            ORG: 'pulse.entity.org',
            LOC: 'pulse.entity.loc',
            ENTITY: 'pulse.entity.default',
        };
        return t(map[type] || 'pulse.entity.default');
    }

    function getSentimentMeta(score: number) {
        if (score > 0.1) {
            return {
                label: t('pulse.sentiment_positive'),
                tone: 'positive' as const,
                barPct: Math.min(100, Math.round(score * 100)),
            };
        }
        if (score < -0.1) {
            return {
                label: t('pulse.sentiment_critical'),
                tone: 'critical' as const,
                barPct: Math.min(100, Math.round(Math.abs(score) * 100)),
            };
        }
        return {
            label: t('pulse.sentiment_neutral'),
            tone: 'neutral' as const,
            barPct: 12,
        };
    }

    return (
        <div className="pulse-client-container w-full max-w-full overflow-x-hidden">
            {/* Category Filter Bar */}
            <nav className="pulse-category-nav">
                <button
                    onClick={() => setCategory(null)}
                    className={`pulse-category-pill ${category === null ? 'active' : 'inactive'}`}
                >
                    {t('pulse.all_categories')}
                </button>
                {categories.map(cat => (
                    <button
                        key={cat}
                        onClick={() => setCategory(cat)}
                        className={`pulse-category-pill ${category === cat ? 'active' : 'inactive'}`}
                    >
                        {cat}
                    </button>
                ))}
                {loading && <Loader2 size={14} className="animate-spin text-presek-mark ml-2" />}
            </nav>

            <details className="pulse-analytics-details mb-8 md:mb-10">
                <summary className="pulse-analytics-summary">
                    <span className="pulse-analytics-title">{t('pulse.analytics_panel')}</span>
                    <span className="pulse-analytics-hint">{t('pulse.analytics_panel_hint')}</span>
                </summary>
                <div className="pulse-analytics-body">
            {/* COMMAND CENTER GRID */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 md:gap-[var(--grid-gap)] mb-8 md:mb-10">
                <div className="lg:col-span-2">
                    <Suspense fallback={<PulseChartFallback tall />}>
                        <PulseHeatmapIsland lang={locale} />
                    </Suspense>
                </div>
                <div className="grid grid-cols-1 gap-[var(--grid-gap)]">
                    <Suspense fallback={<PulseChartFallback />}>
                        <DivergenceGaugeIsland
                            pluralism_pct={intelligence.pluralism?.pluralism_pct}
                            high_consensus_pct={intelligence.pluralism?.high_consensus_pct}
                            lang={locale}
                        />
                    </Suspense>
                    <Suspense fallback={<PulseChartFallback />}>
                        <SentimentRadarIsland data={topicPulse} lang={locale} />
                    </Suspense>
                </div>
            </div>
                </div>
            </details>

            <div className={`pulse-stats-grid mb-8 md:mb-10 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                <div className="pulse-glow-card animate-fade-in" title={t('pulse.rhythm_title')}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Activity size={12}/> {t('pulse.rhythm_label')}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{formatCount(globalPulse?.last_24h)}</p>
                    <div className="card-sparkline group mt-4 flex items-end gap-1 h-12">
                        {velocityData.length > 0 ? (() => {
                            const maxVelocity = Math.max(1, ...velocityData.map((d: any) => d.n || 0));
                            return velocityData.slice(-12).map((v: any, i: number) => {
                                const height = Math.max(15, ((v.n || 0) / maxVelocity) * 100);
                                return (
                                    <div
                                        key={i}
                                        className="bar animate-rise flex-1 bg-presek-mark/40 group-hover:bg-presek-mark hover:!bg-presek-mark transition-all rounded-t-sm"
                                        style={{
                                            height: `${height}%`,
                                            animationDelay: `${i * 0.05}s`
                                        }}
                                    ></div>
                                );
                            });
                        })() : (
                            <div className="w-full h-px bg-border opacity-20 self-center"></div>
                        )}
                    </div>
                </div>

                <div className="pulse-glow-card accent-border animate-fade-in" title={t('pulse.pluralism_title')}>
                    <p className="card-label !text-presek-mark flex items-center gap-1"><ShieldCheck size={12}/> {t('pulse.pluralism_label')}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{intelligence.pluralism?.pluralism_pct > 0 ? `${intelligence.pluralism?.pluralism_pct}%` : '–'}</p>
                    <p className="card-note text-[11px] text-muted-foreground mt-4">{intelligence.pluralism?.pluralism_pct > 0 ? t('pulse.pluralism_consensus').replace('{pct}', String(intelligence.pluralism?.high_consensus_pct)) : t('pulse.analyzing')}</p>
                </div>

                <div className="pulse-glow-card animate-fade-in" title={t('pulse.world_title')}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Globe size={12}/> {t('pulse.world_label')}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{intelligence.international_share_pct > 0 ? `${intelligence.international_share_pct}%` : '–'}</p>
                    <p className="card-note text-[11px] text-muted-foreground mt-4">{t('pulse.world_note')}</p>
                </div>

                <div className="pulse-glow-card animate-fade-in" title={t('pulse.trending_title')}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Zap size={12}/> {t('pulse.trending')} {category && <span className="text-[11px] md:text-[11px] opacity-60">{t('pulse.trending_in').replace('{category}', category)}</span>}</p>
                    <div className="card-list mt-2 flex flex-col gap-1.5">
                        {topEntities.length > 0 ? topEntities.slice(0, 3).map((e: any, i: number) => (
                            <a key={i} href={`/subjekt/${encodeURIComponent(e.name)}`} className="list-item group/item flex items-center justify-between text-xs transition-colors hover:text-presek-mark">
                                <span className="truncate pr-2 font-bold">{e.name}</span>
                                <strong className="text-presek-mark flex items-center gap-0.5 whitespace-nowrap">
                                    +{e.total_mentions}
                                    <ChevronRight size={10} className="opacity-0 group-hover/item:opacity-100 -translate-x-1 group-hover/item:translate-x-0 transition-all" />
                                </strong>
                            </a>
                        )) : (
                            <p className="text-[11px] md:text-[11px] text-muted-foreground italic py-2">{t('pulse.insufficient_data')}</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Quick Insights Deck */}
            <div className="pulse-premium-card mb-10 md:mb-14 flex flex-col md:flex-row gap-4 md:gap-[var(--grid-gap)] items-start md:items-center border-l-4 border-l-presek-mark shadow-premium backdrop-blur-md">
                <div className="flex-1 w-full">
                    <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] mb-2">
                         <h3 className="ui-kicker ui-kicker--accent">{t('pulse.key_insights')}</h3>
                         <span className="h-px flex-1 bg-presek-mark/10"></span>
                    </div>
                    <p className="font-serif italic text-base md:text-xl leading-snug">
                        {intelligence.pluralism?.pluralism_pct > 50
                            ? t('pulse.insight_high_consensus')
                            : intelligence.pluralism?.pluralism_pct > 0
                                ? t('pulse.insight_low_pluralism')
                                : t('pulse.analyzing')
                        }
                    </p>
                </div>
                <div className="flex-1 w-full grid grid-cols-2 gap-3 md:gap-[var(--grid-gap)] border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-8">
                    <div className="group cursor-help relative">
                        <div className="flex items-center gap-1.5 mb-1">
                            <span className="block ui-kicker">{t('pulse.transparency')}</span>
                            <Info size={8} className="opacity-40 group-hover:opacity-100" />
                        </div>
                        <span className="text-lg md:text-xl font-black">{intelligence.synthesis_transparency?.systemic_ratio > 0 ? `${intelligence.synthesis_transparency?.systemic_ratio}%` : '–'}</span>
                        <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-1 z-50 w-48 font-sans left-0 md:left-auto">
                            {t('pulse.transparency_tip')}
                        </div>
                    </div>
                    <div>
                        <span className="block ui-kicker mb-1">{t('pulse.stability')}</span>
                        <div className="flex items-center gap-2 md:gap-[var(--grid-gap)]">
                             <span className="text-lg md:text-xl font-black text-emerald-600">{t('pulse.stability_optimal')}</span>
                             <div className="flex gap-0.5">
                                 <div className="w-1 h-3 bg-emerald-500 rounded-full animate-pulse"></div>
                                 <div className="w-1 h-3 bg-emerald-500/60 rounded-full animate-pulse delay-75"></div>
                                 <div className="w-1 h-3 bg-emerald-500/30 rounded-full animate-pulse delay-150"></div>
                             </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="broadsheet-grid">
                <div className="broadsheet-main">
                    {/* 1. HORIZON ANALYSIS */}
                    <section className="mb-12 md:mb-16">
                        <div className="flex flex-col items-start gap-2 md:flex-row md:items-center md:justify-between mb-5 md:mb-8 border-b border-border pb-3 md:pb-4">
                            <h2 className="section-title-italic !mb-0 text-[1.45rem] md:text-3xl">{t('pulse.horizon_title')}</h2>
                            <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] ui-kicker">
                                <BarChart3 size={12} /> {t('pulse.horizon_kicker')}
                            </div>
                        </div>
                        <Suspense fallback={<PulseChartFallback tall />}>
                            <PulseLandscapeIsland data={pulseData} loading={loading} lang={locale} onSourceClick={(s) => {
                                const el = document.getElementById('leaderboard');
                                if (el) el.scrollIntoView({ behavior: 'smooth' });
                            }} />
                        </Suspense>
                    </section>

                    {/* 2. KEY ACTORS GRID */}
                    <section className="mb-14 md:mb-20">
                        <div className="flex flex-col items-start gap-2 md:flex-row md:items-center md:justify-between mb-5 md:mb-8 border-b border-border pb-3 md:pb-4">
                            <h2 className="section-title-italic !mb-0 text-[1.45rem] md:text-3xl">{t('pulse.actors_title')}</h2>
                            <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] ui-kicker">
                                <Users size={12} /> {t('pulse.actors_kicker')}
                            </div>
                        </div>

                        {loading ? (
                            <div className="actor-grid-box animate-pulse">
                                {[1, 2, 3].map(i => (
                                    <div key={i} className="h-48 border border-border bg-card/50 rounded-2xl"></div>
                                ))}
                            </div>
                        ) : topEntities.length > 0 ? (
                            <div className="actor-grid-box">
                                {topEntities.map((ent: any, index: number) => {
                                    const score = Number(ent.sentiment_score) || 0;
                                    const sentiment = getSentimentMeta(score);
                                    return (
                                        <a
                                            key={ent.name}
                                            href={`/subjekt/${encodeURIComponent(ent.name)}`}
                                            className={`actor-card group ${index === 0 ? 'actor-card--featured' : ''}`}
                                        >
                                            <div className="actor-card-top">
                                                <span className="actor-type-chip">{getTypeLabel(ent.type)}</span>
                                                {index === 0 && (
                                                    <span className="actor-rank-badge">#1</span>
                                                )}
                                            </div>
                                            <h3 className="actor-card-name">{ent.name}</h3>
                                            <div className="actor-sentiment-row">
                                                <span className={`actor-sentiment-label tone-${sentiment.tone}`}>
                                                    {sentiment.label}
                                                </span>
                                                <div className="actor-sentiment-track" aria-hidden="true">
                                                    <div
                                                        className={`actor-sentiment-fill tone-${sentiment.tone}`}
                                                        style={{ width: `${sentiment.barPct}%` }}
                                                    />
                                                </div>
                                            </div>
                                            <div className="actor-card-footer">
                                                <div className="actor-mentions">
                                                    <span className="actor-mentions-label">{t('pulse.mentions')}</span>
                                                    <span className="actor-mentions-value tabular-nums">
                                                        {ent.total_mentions > 0 ? ent.total_mentions : '–'}
                                                    </span>
                                                </div>
                                            </div>
                                        </a>
                                    );
                                })}
                            </div>
                        ) : (
                            <div className="py-20 text-center border border-dashed border-border rounded-2xl bg-secondary/5">
                                <Users className="mx-auto mb-4 opacity-10" size={48} />
                                <p className="font-serif italic text-muted-foreground text-lg">{t('pulse.analyzing_actors')}</p>
                            </div>
                        )}
                    </section>
                </div>

                <aside className="broadsheet-rail">
                    <PresekAdRailSlot lang={locale} />
                    <section className="pulse-premium-card mb-6">
                        <p className="rail-kicker ui-kicker ui-kicker--accent">{t('pulse.methodology')}</p>
                        <h3 className="rail-title italic font-serif text-lg font-black mt-1 mb-2">{t('pulse.algorithm_title')}</h3>
                        <p className="rail-text text-xs text-muted-foreground leading-relaxed">
                            {t('pulse.algorithm_body')}
                        </p>
                    </section>

                    <div className="pulse-premium-card">
                        <h4 className="sidebar-label !border-presek-mark text-presek-mark">{t('pulse.compare_sources')}</h4>
                        <div className="mt-4">
                            <SourceComparisonIsland allSources={pulseData.map((r: PulseRow) => r.source)} lang={locale} />
                        </div>
                    </div>
                </aside>
            </div>

            {/* Transparency Scoreboard */}
            <section className="mt-14 md:mt-20">
                <div className="section-heading-row masthead-double-rule mb-5 md:mb-8">
                    <h2 className="section-title-italic !mb-0">{t('pulse.transparency_index')}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-[var(--grid-gap)]">
                    <div className="pulse-premium-card !border-l-4 !border-l-emerald-500 shadow-premium backdrop-blur-md">
                        <h4 className="sidebar-label !border-emerald-500 !text-emerald-700 dark:!text-emerald-400 mb-4 md:mb-6">{t('pulse.most_objective')}</h4>
                        <div className="flex flex-col gap-[var(--grid-gap)]">
                            {[...pulseLeaders].sort((a,b) => b.avg_objectivity - a.avg_objectivity).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-emerald-600 transition-colors">{s.source}</span>
                                    <span className="text-[11px] md:text-xs font-black text-emerald-600">{s.avg_objectivity > 0 ? (s.avg_objectivity * 100).toFixed(0) + t('pulse.objectivity_pct') : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="pulse-premium-card !border-l-4 !border-l-red-500 shadow-premium backdrop-blur-md">
                        <h4 className="sidebar-label !border-red-500 !text-red-700 dark:!text-red-400 mb-4 md:mb-6">{t('pulse.lowest_sensationalism')}</h4>
                        <div className="flex flex-col gap-[var(--grid-gap)]">
                            {[...pulseLeaders].sort((a,b) => a.avg_sensationalism - b.avg_sensationalism).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-red-600 transition-colors">{s.source}</span>
                                    <span className="text-[11px] md:text-xs font-black text-red-600">{s.avg_sensationalism > 0 ? (s.avg_sensationalism * 100).toFixed(0) + t('pulse.sensation_pct') : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {(!loading || pulseLeaders.length > 0) && (
                <section id="leaderboard" className={`mt-16 md:mt-24 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                    <div className="section-heading-row masthead-double-rule mb-5 md:mb-8">
                        <h2 className="section-title-italic !mb-0">{t('pulse.leaderboard_title')}</h2>
                    </div>
                    <div className="pulse-table-wrapper">
                        <table className="pulse-table">
                            <thead>
                                <tr>
                                    <th title={t('pulse.table.newsroom_tip')}>{t('pulse.table.newsroom')}</th>
                                    <th title={t('pulse.table.tone_tip')}>{t('pulse.table.tone')}</th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>{t('pulse.table.objectivity')}</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal text-left">
                                                {t('pulse.table.objectivity_tip')}
                                            </div>
                                        </div>
                                    </th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>{t('pulse.table.sensationalism')}</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal text-left">
                                                {t('pulse.table.sensationalism_tip')}
                                            </div>
                                        </div>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {pulseLeaders.map((row: PulseRow) => (
                                    <tr key={row.source}>
                                        <td>
                                            <div className="pulse-table-source-info">
                                                <strong>{row.source}</strong>
                                                <span>{row.cluster_count} {t('pulse.table.topics')}</span>
                                            </div>
                                        </td>
                                        <td><span className={`tone-label ${getSentimentIcon(row.avg_sentiment).color}`} title={getSentimentIcon(row.avg_sentiment).title}>{getSentimentIcon(row.avg_sentiment).icon}</span></td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="pulse-bar-track shadow-inner">
                                                    <div className="pulse-bar-fill" style={{ width: `${row.avg_objectivity * 100}%` }}></div>
                                                </div>
                                                <span className="stat-num">{formatStat(row.avg_objectivity)}</span>
                                                <div className="w-8 flex items-center justify-center">
                                                    {row.objectivity_delta !== undefined && row.objectivity_delta !== 0 && (
                                                        <span
                                                            className={`text-[11px] font-black ${row.objectivity_delta > 0 ? 'text-emerald-500' : 'text-nyt-red'}`}
                                                            title={t('pulse.objectivity_delta').replace('{delta}', (row.objectivity_delta * 100).toFixed(1))}
                                                        >
                                                            {row.objectivity_delta > 0 ? '▲' : '▼'}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="pulse-bar-track bar-red shadow-inner">
                                                    <div className="pulse-bar-fill" style={{ width: `${row.avg_sensationalism * 100}%` }}></div>
                                                </div>
                                                <span className="stat-num text-nyt-red">{formatStat(row.avg_sensationalism)}</span>
                                                <div className="w-8"></div>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>
            )}
        </div>
    );
}
