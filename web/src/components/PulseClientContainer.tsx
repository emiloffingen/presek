import React, { Suspense, lazy, useState, useEffect, useMemo } from 'react';
import { Activity, Zap, ShieldCheck, Globe, Timer, Loader2, BarChart3, TrendingUp, Users, Info, ChevronRight, Target } from 'lucide-react';
import SourceComparisonIsland from './SourceComparisonIsland';
import TinyAdzRailSlot from './TinyAdzRailSlot';
import { apiBaseUrl } from '../lib/apiBase';
import { useClientTranslations } from '../i18n/clientTranslations';
import { common } from '../i18n/namespaces/common';

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
    const isMK = locale === 'mk';
    const t = useClientTranslations(locale, common);

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
        if (score > 0.2) return { icon: <Activity size={14} />, color: 'text-green-600', title: isMK ? 'Позитивен' : 'Pozitivan' };
        if (score < -0.2) return { icon: <Activity size={14} />, color: 'text-nyt-red', title: isMK ? 'Критичен' : 'Kritičan' };
        return { icon: <Activity size={14} />, color: 'text-muted-foreground', title: isMK ? 'Неутрален' : 'Neutralan' };
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
            'PER': isMK ? 'Личност' : 'Ličnost',
            'ORG': isMK ? 'Организација' : 'Organizacija',
            'LOC': isMK ? 'Локација' : 'Lokacija',
            'ENTITY': isMK ? 'Субјект' : 'Subjekt'
        };
        return map[type] || (isMK ? 'Субјект' : 'Subjekt');
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
                    {isMK ? 'СИТЕ КАТЕГОРИИ' : 'SVE KATEGORIJE'}
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
                {loading && <Loader2 size={14} className="animate-spin text-nyt-accent ml-2" />}
            </nav>

            {/* NEW: COMMAND CENTER GRID */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 md:gap-[var(--grid-gap)] mb-10 md:mb-16">
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

            <div className={`pulse-stats-grid mb-8 md:mb-12 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                <div className="pulse-glow-card animate-fade-in" title={isMK ? "Вкупен број на обработени објави во последните 24 часа." : "Ukupan broj obrađenih objava u poslednja 24 časa."}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Activity size={12}/> {isMK ? 'ИНФОРМАТИВЕН РИТАМ' : 'INFORMATIVNI RITAM'}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{formatCount(globalPulse?.last_24h)}</p>
                    <div className="card-sparkline group mt-4 flex items-end gap-1 h-12">
                        {velocityData.length > 0 ? (() => {
                            const maxVelocity = Math.max(1, ...velocityData.map((d: any) => d.n || 0));
                            return velocityData.slice(-12).map((v: any, i: number) => {
                                const height = Math.max(15, ((v.n || 0) / maxVelocity) * 100);
                                return (
                                    <div
                                        key={i}
                                        className="bar animate-rise flex-1 bg-nyt-accent/40 group-hover:bg-nyt-accent hover:!bg-nyt-accent transition-all rounded-t-sm"
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

                <div className="pulse-glow-card accent-border animate-fade-in" title={isMK ? "Процент на теми покриени од повеќе извори." : "Procenat tema koje su pokrivene od strane više različitih izvora."}>
                    <p className="card-label !text-nyt-accent flex items-center gap-1"><ShieldCheck size={12}/> {isMK ? 'ПЛУРАЛИЗАМ' : 'PLURALIZAM'}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{intelligence.pluralism?.pluralism_pct > 0 ? `${intelligence.pluralism?.pluralism_pct}%` : '–'}</p>
                    <p className="card-note text-[11px] text-muted-foreground mt-4">{intelligence.pluralism?.pluralism_pct > 0 ? `${intelligence.pluralism?.high_consensus_pct}% ${isMK ? 'медиумски консензус' : 'medijski konsenzus'}` : (isMK ? 'Системот анализира...' : 'Sistem analizira...')}</p>
                </div>

                <div className="pulse-glow-card animate-fade-in" title={isMK ? "Процент на меѓународни извори." : "Procenat međunarodnih izvora koji izveštavaju."}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Globe size={12}/> {isMK ? 'СВЕТОТ КАЈ НАС' : 'SVET KOD NAS'}</p>
                    <p className="card-value font-serif text-3xl font-black mt-2">{intelligence.international_share_pct > 0 ? `${intelligence.international_share_pct}%` : '–'}</p>
                    <p className="card-note text-[11px] text-muted-foreground mt-4">{isMK ? 'вести од меѓународни извори' : 'vesti iz međunarodnih izvora'}</p>
                </div>

                <div className="pulse-glow-card animate-fade-in" title={isMK ? "Субјекти кои се моментално најзастапени." : "Subjekti koji su trenutno najzastupljeniji u vestima."}>
                    <p className="card-label text-muted-foreground flex items-center gap-1"><Zap size={12}/> TRENDING {category && <span className="text-[11px] md:text-[11px] opacity-60">{isMK ? `ВО ${category}` : `U ${category}`}</span>}</p>
                    <div className="card-list mt-2 flex flex-col gap-1.5">
                        {topEntities.length > 0 ? topEntities.slice(0, 3).map((e: any, i: number) => (
                            <a key={i} href={`/subjekt/${encodeURIComponent(e.name)}`} className="list-item group/item flex items-center justify-between text-xs transition-colors hover:text-nyt-accent">
                                <span className="truncate pr-2 font-bold">{e.name}</span>
                                <strong className="text-nyt-accent flex items-center gap-0.5 whitespace-nowrap">
                                    +{e.total_mentions}
                                    <ChevronRight size={10} className="opacity-0 group-hover/item:opacity-100 -translate-x-1 group-hover/item:translate-x-0 transition-all" />
                                </strong>
                            </a>
                        )) : (
                            <p className="text-[11px] md:text-[11px] text-muted-foreground italic py-2">{isMK ? 'Нема доволно податоци' : 'Nema dovoljno podataka'}</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Quick Insights Deck */}
            <div className="pulse-premium-card mb-12 md:mb-20 flex flex-col md:flex-row gap-4 md:gap-[var(--grid-gap)] items-start md:items-center border-l-4 border-l-nyt-accent shadow-premium backdrop-blur-md">
                <div className="flex-1 w-full">
                    <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] mb-2">
                         <h3 className="ui-kicker ui-kicker--accent">{isMK ? 'Клучни увиди' : 'Ključni uvidi'}</h3>
                         <span className="h-px flex-1 bg-nyt-accent/10"></span>
                    </div>
                    <p className="font-serif italic text-base md:text-xl leading-snug">
                        {intelligence.pluralism?.pluralism_pct > 50
                            ? (isMK ? "Забележан е висок степен на медиумски консензус кај водечките приказни денес." : "Zabeležen je visok stepen medijskog konsenzusa kod vodećih priča danas.")
                            : intelligence.pluralism?.pluralism_pct > 0
                                ? (isMK ? "Низок плурализам: темите се обработуваат со специфични, дивергентни агли." : "Nizak pluralizam: teme se obrađuju sa specifičnim, divergentnim uglovima.")
                                : (isMK ? "Системот анализира..." : "Sistem analizira...")
                        }
                    </p>
                </div>
                <div className="flex-1 w-full grid grid-cols-2 gap-3 md:gap-[var(--grid-gap)] border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-8">
                    <div className="group cursor-help relative">
                        <div className="flex items-center gap-1.5 mb-1">
                            <span className="block ui-kicker">{isMK ? 'Транспарентност' : 'Transparentnost'}</span>
                            <Info size={8} className="opacity-40 group-hover:opacity-100" />
                        </div>
                        <span className="text-lg md:text-xl font-black">{intelligence.synthesis_transparency?.systemic_ratio > 0 ? `${intelligence.synthesis_transparency?.systemic_ratio}%` : '–'}</span>
                        <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-1 z-50 w-48 font-sans left-0 md:left-auto">
                            {isMK ? 'Процент на објави чија содржина е потврдена преку системот.' : 'Procenat objava čija je sadržina potvrđena kroz sistem.'}
                        </div>
                    </div>
                    <div>
                        <span className="block ui-kicker mb-1">{isMK ? 'Стабилност' : 'Stabilnost'}</span>
                        <div className="flex items-center gap-2 md:gap-[var(--grid-gap)]">
                             <span className="text-lg md:text-xl font-black text-emerald-600">{isMK ? 'Оптимална' : 'Optimalna'}</span>
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
                            <h2 className="section-title-italic !mb-0 text-[1.45rem] md:text-3xl">{isMK ? 'Редакциски Хоризонт' : 'Redakcijski Horizont'}</h2>
                            <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] ui-kicker">
                                <BarChart3 size={12} /> {isMK ? 'Аналитика по теми' : 'Analitika po temama'}
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
                            <h2 className="section-title-italic !mb-0 text-[1.45rem] md:text-3xl">{isMK ? 'Клучни актери' : 'Ključni akteri'}</h2>
                            <div className="flex items-center gap-2 md:gap-[var(--grid-gap)] ui-kicker">
                                <Users size={12} /> {isMK ? 'во фокус' : 'u fokusu'}
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
                                <p className="font-serif italic text-muted-foreground text-lg">{isMK ? 'Системот анализира нови актери во оваа категорија...' : 'Sistem analizira nove aktere u ovoj kategoriji...'}</p>
                            </div>
                        )}
                    </section>
                </div>

                <aside className="broadsheet-rail">
                    <TinyAdzRailSlot lang={locale} />
                    <section className="pulse-premium-card mb-6">
                        <p className="rail-kicker ui-kicker ui-kicker--accent">{isMK ? 'Методологија' : 'Metodologija'}</p>
                        <h3 className="rail-title italic font-serif text-lg font-black mt-1 mb-2">{isMK ? 'Уреднички Алгоритам' : 'Urednički Algoritam'}</h3>
                        <p className="rail-text text-xs text-muted-foreground leading-relaxed">
                            {isMK
                              ? 'Информациите во овој индекс се генерираат преку автоматска обработка на природен јазик (NLP) на сите вклучени извори за изминатите 24 часа.'
                              : 'Informacije u ovom indeksu generišu se putem automatske obrade prirodnog jezika (NLP) na svim uključenim srpskim izvorima za protekla 24 časa.'}
                        </p>
                    </section>

                    <div className="pulse-premium-card">
                        <h4 className="sidebar-label !border-nyt-accent text-nyt-accent">{isMK ? 'СПОРЕДБА НА ИЗВОРИ' : 'POREĐENJE IZVORA'}</h4>
                        <div className="mt-4">
                            <SourceComparisonIsland allSources={pulseData.map((r: PulseRow) => r.source)} lang={locale} />
                        </div>
                    </div>
                </aside>
            </div>

            {/* Transparency Scoreboard */}
            <section className="mt-14 md:mt-20">
                <div className="section-heading-row masthead-double-rule mb-5 md:mb-8">
                    <h2 className="section-title-italic !mb-0">{isMK ? 'Индекс на Транспарентност' : 'Indeks Transparentnosti'}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-[var(--grid-gap)]">
                    <div className="pulse-premium-card !border-l-4 !border-l-emerald-500 shadow-premium backdrop-blur-md">
                        <h4 className="sidebar-label !border-emerald-500 !text-emerald-700 dark:!text-emerald-400 mb-4 md:mb-6">{isMK ? 'Најобјективни извори (24ч)' : 'Najobjektivniji izvori (24h)'}</h4>
                        <div className="flex flex-col gap-[var(--grid-gap)]">
                            {[...pulseLeaders].sort((a,b) => b.avg_objectivity - a.avg_objectivity).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-emerald-600 transition-colors">{s.source}</span>
                                    <span className="text-[11px] md:text-xs font-black text-emerald-600">{s.avg_objectivity > 0 ? (s.avg_objectivity * 100).toFixed(0) + (isMK ? '% Објективност' : '% Objektivnost') : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="pulse-premium-card !border-l-4 !border-l-red-500 shadow-premium backdrop-blur-md">
                        <h4 className="sidebar-label !border-red-500 !text-red-700 dark:!text-red-400 mb-4 md:mb-6">{isMK ? 'Најнизок сензационализам' : 'Najniži senzacionalizam'}</h4>
                        <div className="flex flex-col gap-[var(--grid-gap)]">
                            {[...pulseLeaders].sort((a,b) => a.avg_sensationalism - b.avg_sensationalism).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-red-600 transition-colors">{s.source}</span>
                                    <span className="text-[11px] md:text-xs font-black text-red-600">{s.avg_sensationalism > 0 ? (s.avg_sensationalism * 100).toFixed(0) + (isMK ? '% Сензација' : '% Senzacija') : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {(!loading || pulseLeaders.length > 0) && (
                <section id="leaderboard" className={`mt-16 md:mt-24 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                    <div className="section-heading-row masthead-double-rule mb-5 md:mb-8">
                        <h2 className="section-title-italic !mb-0">{isMK ? 'Ранг листа на редакции (24ч)' : 'Rang lista redakcija (24h)'}</h2>
                    </div>
                    <div className="pulse-table-wrapper">
                        <table className="pulse-table">
                            <thead>
                                <tr>
                                    <th title={isMK ? "Медиум или извор на информации" : "Medij ili izvor informacija"}>{isMK ? 'РЕДАКЦИЈА' : 'REDAKCIJA'}</th>
                                    <th title={isMK ? "Просечен тон" : "Prosečan sentiment (pozitivan, negativan, neutralan)"}>{isMK ? 'ТОН' : 'TON'}</th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>{isMK ? 'ОБЈЕКТИВНОСТ' : 'OBJEKTIVNOST'}</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal text-left">
                                                {isMK ? 'Фактичко известување без субјективни коментари.' : 'Faktičko izveštavanje bez subjektivnih komentara.'}
                                            </div>
                                        </div>
                                    </th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>{isMK ? 'СЕНЗАЦИОНАЛИЗАМ' : 'SENZACIONALIZAM'}</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[11px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal text-left">
                                                {isMK ? 'Употреба на емотивно набиен или преувеличен речник.' : 'Upotreba emotivno nabijenog ili preuveličanog rečnika.'}
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
                                                <span>{row.cluster_count} {isMK ? 'теми' : 'tema'}</span>
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
                                                            title={isMK ? `Промена во однос на 7-дневен просек: ${(row.objectivity_delta * 100).toFixed(1)}%` : `Promena u odnosu na 7-dnevni prosek: ${(row.objectivity_delta * 100).toFixed(1)}%`}
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
