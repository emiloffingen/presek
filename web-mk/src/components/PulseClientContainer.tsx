import React, { useState, useEffect, useMemo } from 'react';
import { Activity, Zap, ShieldCheck, Globe, Timer, Loader2, BarChart3, TrendingUp, Users, Info, ChevronRight } from 'lucide-react';
import PulseLandscapeIsland from './PulseLandscapeIsland';
import SourceComparisonIsland from './SourceComparisonIsland';
import { apiBaseUrl } from '../lib/apiBase';

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
}

export default function PulseClientContainer({ initialGlobalPulse, initialPulseData, categories, ssrFailed }: PulseClientContainerProps) {
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
                const catParam = category ? `?category=${encodeURIComponent(category)}` : '';
                const [pulseRes, globalRes] = await Promise.all([
                    fetch(`${API_URL}/intelligence/source-pulse${catParam}`),
                    fetch(`${API_URL}/intelligence/global-pulse${catParam}`)
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
    }, [category]);

    const intelligence = globalPulse?.intelligence ?? {};
    const velocityData = globalPulse?.velocity ?? [];
    const topEntities = globalPulse?.top_entities ?? [];
    const topicPulse = globalPulse?.by_topic_sentiment ?? [];
    const pulseLeaders = pulseData.slice(0, 15);

    function getSentimentIcon(score: number) {
        if (score > 0.2) return { icon: <Activity size={14} />, color: 'text-green-600', title: 'Pozitiven' };
        if (score < -0.2) return { icon: <Activity size={14} />, color: 'text-nyt-red', title: 'Kriticen' };
        return { icon: <Activity size={14} />, color: 'text-muted-foreground', title: 'Neutralen' };
    }

    function formatStat(val: number) {
        if (val === 0 || !val) return '–';
        return (val * 100).toFixed(0) + '%';
    }

    function getTypeLabel(type: string) {
        const map: Record<string, string> = {
            'PER': 'Licnost',
            'ORG': 'Organizacija',
            'LOC': 'Lokacija',
            'ENTITY': 'Subjekt'
        };
        return map[type] || 'Subjekt';
    }

    return (
        <div className="pulse-client-container w-full max-w-full overflow-x-hidden">
            {/* Category Filter Bar */}
            <nav className="flex items-center gap-2 mb-12 border-b border-border pb-4 overflow-x-auto hide-scrollbar sticky top-[72px] bg-background/80 backdrop-blur-md z-30 py-2">
                <button 
                    onClick={() => setCategory(null)}
                    className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all whitespace-nowrap ${category === null ? 'bg-nyt-accent text-white' : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'}`}
                >
                    SITE KATEGORII
                </button>
                {categories.map(cat => (
                    <button 
                        key={cat}
                        onClick={() => setCategory(cat)}
                        className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all whitespace-nowrap ${category === cat ? 'bg-nyt-accent text-white' : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'}`}
                    >
                        {cat}
                    </button>
                ))}
                {loading && <Loader2 size={14} className="animate-spin text-nyt-accent ml-2" />}
            </nav>

            <div className={`pulse-stats-grid mb-12 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                <div className="pulse-card" title="Vkupen broj na obraboteni objavi vo poslednite 24 casa.">
                    <p className="card-label"><Activity size={12}/> INFORMATIVEN RITAM</p>
                    <p className="card-value">{globalPulse?.last_24h?.toLocaleString('mk-RS') || '–'}</p>
                    <div className="card-sparkline group">
                        {velocityData.length > 0 ? (() => {
                            const maxVelocity = Math.max(1, ...velocityData.map((d: any) => d.n || 0));
                            return velocityData.slice(-12).map((v: any, i: number) => {
                                const height = Math.max(15, ((v.n || 0) / maxVelocity) * 100);
                                return (
                                    <div 
                                        key={i} 
                                        className="bar animate-rise" 
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

                <div className="pulse-card border-t-4 border-t-nyt-accent" title="Procent na temi koi se pokrieni od povece razliciti izvori (pokazuva mediumski fokus).">
                    <p className="card-label !text-nyt-accent"><ShieldCheck size={12}/> PLURALIZAM</p>
                    <p className="card-value">{intelligence.pluralism?.pluralism_pct > 0 ? `${intelligence.pluralism?.pluralism_pct}%` : '–'}</p>
                    <p className="card-note">{intelligence.pluralism?.pluralism_pct > 0 ? `${intelligence.pluralism?.high_consensus_pct}% mediumski konsenzus` : 'Sistemot analizira novi klasteri'}</p>
                </div>

                <div className="pulse-card" title="Procent na medjunarodni izvori sto izvestuvaat.">
                    <p className="card-label"><Globe size={12}/> SVETOT KAJ NAS</p>
                    <p className="card-value">{intelligence.international_share_pct > 0 ? `${intelligence.international_share_pct}%` : '–'}</p>
                    <p className="card-note">vesti od medjunarodni izvori</p>
                </div>

                <div className="pulse-card" title="Subjekti koi momentalno se najzastapeni vo vestite.">
                    <p className="card-label"><Zap size={12}/> TRENDING {category && <span className="text-[8px] opacity-60">VO {category}</span>}</p>
                    <div className="card-list">
                        {topEntities.length > 0 ? topEntities.slice(0, 3).map((e: any, i: number) => (
                            <a key={i} href={`/subjekt/${encodeURIComponent(e.name)}`} className="list-item group/item">
                                <span className="truncate group-hover/item:text-nyt-accent transition-colors">{e.name}</span>
                                <strong className="text-nyt-accent flex items-center gap-1">
                                    +{e.total_mentions}
                                    <ChevronRight size={10} className="opacity-0 group-hover/item:opacity-100 -translate-x-1 group-hover/item:translate-x-0 transition-all" />
                                </strong>
                            </a>
                        )) : (
                            <p className="text-[10px] text-muted-foreground italic py-2">Nema dovolno podatoci za trendovi</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Quick Insights Deck */}
            <div className="bg-secondary/10 border border-border p-6 rounded-lg mb-20 flex flex-col md:flex-row gap-6 md:gap-8 items-start md:items-center border-l-4 border-l-nyt-accent shadow-sm">
                <div className="flex-1 w-full">
                    <div className="flex items-center gap-2 mb-2">
                         <h3 className="text-[11px] font-black uppercase tracking-widest text-nyt-accent">Kljucni uvidi</h3>
                         <span className="h-px flex-1 bg-nyt-accent/10"></span>
                    </div>
                    <p className="font-serif italic text-lg md:text-xl leading-snug">
                        {intelligence.pluralism?.pluralism_pct > 50 
                            ? "Zabelezan e visok stepen na mediumski konsenzus kaj vodeckite storii danas."
                            : intelligence.pluralism?.pluralism_pct > 0
                                ? "Nizok pluralizam: temite se obrabotuvaat so specificni, divergentni agli."
                                : "Sistemot analizira..."
                        }
                    </p>
                </div>
                <div className="flex-1 w-full grid grid-cols-2 gap-6 md:gap-8 border-t md:border-t-0 md:border-l border-border pt-6 md:pt-0 md:pl-8">
                    <div className="group cursor-help relative">
                        <div className="flex items-center gap-1.5 mb-1">
                            <span className="block text-[9px] font-black uppercase text-muted-foreground">Transparentnost</span>
                            <Info size={8} className="opacity-40 group-hover:opacity-100" />
                        </div>
                        <span className="text-xl font-black">{intelligence.synthesis_transparency?.systemic_ratio > 0 ? `${intelligence.synthesis_transparency?.systemic_ratio}%` : '–'}</span>
                        <div className="absolute hidden group-hover:block bg-foreground text-background text-[10px] p-2 rounded shadow-xl mt-1 z-50 w-48 font-sans left-0 md:left-auto">
                            Procent na objavi cija sodrzina e potvrdena niz sistemot.
                        </div>
                    </div>
                    <div>
                        <span className="block text-[9px] font-black uppercase text-muted-foreground mb-1">Stabilnost</span>
                        <div className="flex items-center gap-2">
                             <span className="text-xl font-black text-emerald-600">Optimalna</span>
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
                    <section className="mb-16">
                        <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                            <h2 className="section-title-italic !mb-0 text-3xl">Redakciski Horizont</h2>
                            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                                <BarChart3 size={12} /> Analitika po temi
                            </div>
                        </div>
                        <PulseLandscapeIsland data={pulseData} loading={loading} onSourceClick={(s) => {
                            // Focus Mode Logic: Maybe show a specific modal or filter?
                            // For now, let's scroll to the table and highlight or search?
                            // Let's implement a simple scroll to table for now.
                            const el = document.getElementById('leaderboard');
                            if (el) el.scrollIntoView({ behavior: 'smooth' });
                        }} />
                    </section>

                    {/* 1b. TOPIC PULSE */}
                    {topicPulse.length > 0 && (
                        <section className="mb-16">
                            <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                                <h2 className="section-title-italic !mb-0 text-3xl">Tematski Puls</h2>
                                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                                    <Zap size={12} /> vo poslednite 24c
                                </div>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {topicPulse.slice(0, 6).map((tp: any) => (
                                    <div key={tp.topic} className="p-4 border border-border bg-secondary/5 hover:bg-secondary/10 transition-colors border-l-2 border-l-nyt-accent flex items-center justify-between">
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-black uppercase text-nyt-accent mb-1">{tp.topic}</span>
                                            <span className="text-xs font-serif italic text-muted-foreground">{tp.n > 0 ? tp.n + ' storii analizirani' : '–'}</span>
                                        </div>
                                        <div className="flex gap-6 items-center">
                                            <div className="flex flex-col items-end">
                                                <span className="text-[8px] font-black uppercase opacity-50">Objektivnost</span>
                                                <span className="text-sm font-black">{tp.avg_objectivity > 0 ? (tp.avg_objectivity * 100).toFixed(0) + '%' : '–'}</span>
                                            </div>
                                            <div className="flex flex-col items-end">
                                                <span className="text-[8px] font-black uppercase opacity-50">Senzacija</span>
                                                <span className={`text-sm font-black ${tp.avg_sensationalism > 0.4 ? 'text-nyt-red' : 'text-emerald-600'}`}>
                                                    {tp.avg_sensationalism > 0 ? (tp.avg_sensationalism * 100).toFixed(0) + '%' : '–'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {/* 2. KEY ACTORS GRID */}
                    <section className="mb-20">
                        <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                            <h2 className="section-title-italic !mb-0 text-3xl">Kljucni akteri</h2>
                            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                                <Users size={12} /> vo fokus
                            </div>
                        </div>
                        
                        {loading ? (
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 animate-pulse">
                                {[1, 2, 3].map(i => (
                                    <div key={i} className="h-48 border border-border bg-card/50"></div>
                                ))}
                            </div>
                        ) : topEntities.length > 0 ? (
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                                {topEntities.map((ent: any) => (
                                    <a 
                                        key={ent.name} 
                                        href={`/subjekt/${encodeURIComponent(ent.name)}`}
                                        className="p-6 border border-border bg-card hover:border-nyt-accent hover:shadow-xl transition-all group relative overflow-hidden flex flex-col"
                                    >
                                        <div className="absolute top-0 left-0 w-1 h-full bg-nyt-accent/10 group-hover:bg-nyt-accent transition-colors"></div>
                                        <div className="flex justify-between items-start mb-4">
                                            <span className="text-[9px] font-black uppercase text-nyt-accent tracking-widest bg-nyt-accent/5 px-2 py-0.5 rounded">
                                                {getTypeLabel(ent.type)}
                                            </span>
                                            <span className="text-xl group-hover:scale-125 transition-transform">{ent.sentiment_score > 0.1 ? '😊' : ent.sentiment_score < -0.1 ? '😤' : '😐'}</span>
                                        </div>
                                        <h3 className="font-serif font-black text-xl leading-tight group-hover:text-nyt-accent mb-6">{ent.name}</h3>
                                        <div className="mt-auto pt-4 border-t border-border/40 flex items-center justify-between">
                                            <div className="flex flex-col">
                                                <span className="text-[10px] font-bold text-muted-foreground uppercase">Spomenuvanja</span>
                                                <span className="text-xl font-black tabular-nums">{ent.total_mentions > 0 ? ent.total_mentions : '–'}</span>
                                            </div>
                                            <div className={`text-[10px] font-black uppercase tracking-tighter ${ent.sentiment_score > 0.1 ? 'text-green-600' : ent.sentiment_score < -0.1 ? 'text-red-600' : 'text-muted-foreground'}`}>
                                                {ent.sentiment_score > 0.1 ? 'Pozitiven' : ent.sentiment_score < -0.1 ? 'Kriticen' : 'Neutralen'}
                                            </div>
                                        </div>
                                    </a>
                                ))}
                            </div>
                        ) : (
                            <div className="py-20 text-center border border-dashed border-border rounded-2xl bg-secondary/5">
                                <Users className="mx-auto mb-4 opacity-10" size={48} />
                                <p className="font-serif italic text-muted-foreground text-lg">Sistemot analizira novi akteri vo ova kategorija...</p>
                            </div>
                        )}
                    </section>
                </div>

                <aside className="broadsheet-rail">
                    <section className="rail-block">
                        <p className="rail-kicker">Metodologija</p>
                        <h3 className="rail-title italic font-serif text-lg">Urednicki Algoritam</h3>
                        <p className="rail-text">
                            Informacije u ovom indeksu generišu se putem automatske obrade prirodnog jezika (NLP) na svim uključenim srpskim izvorima za proteklih 24 časa.
                        </p>
                    </section>

                    <section className="rail-block mt-12">
                         <p className="rail-kicker">Tematska Tenzija</p>
                         <h3 className="rail-title italic font-serif text-lg">Emocionalen Pejzaz</h3>
                         <div className="flex flex-col gap-3 mt-4">
                             {topicPulse.slice(0, 5).map((tp: any) => {
                                 const tension = (1 - tp.avg_objectivity) * 100;
                                 return (
                                     <div key={tp.topic} className="space-y-1">
                                         <div className="flex justify-between text-[10px] font-bold uppercase tracking-tighter">
                                             <span>{tp.topic}</span>
                                             <span className={tension > 60 ? 'text-nyt-red' : 'text-muted-foreground'}>{tension > 0 ? tension.toFixed(0) + '%' : '–'}</span>
                                         </div>
                                         <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                                             <div 
                                                className={`h-full transition-all duration-1000 ${tension > 60 ? 'bg-nyt-red' : 'bg-nyt-accent'}`} 
                                                style={{ width: `${tension}%` }}
                                            ></div>
                                         </div>
                                     </div>
                                 );
                             })}
                         </div>
                    </section>

                    <div className="sidebar-module mt-12">
                        <h4 className="sidebar-label">SPOREDBA NA izvori</h4>
                        <div className="mt-4">
                            <SourceComparisonIsland allSources={pulseData.map((r: PulseRow) => r.source)} />
                        </div>
                    </div>
                </aside>
            </div>

            {/* Transparency Scoreboard */}
            <section className="mt-20">
                <div className="section-heading-row masthead-double-rule mb-8">
                    <h2 className="section-title-italic !mb-0">Indeks na Transparentnost</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="border border-border p-6 bg-emerald-50/50 dark:bg-emerald-950/10 border-l-4 border-l-emerald-500">
                        <h4 className="sidebar-label !border-emerald-500 !text-emerald-700 dark:!text-emerald-400 mb-6">Najobjektivni izvori (24c)</h4>
                        <div className="flex flex-col gap-4">
                            {[...pulseLeaders].sort((a,b) => b.avg_objectivity - a.avg_objectivity).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-emerald-600 transition-colors">{s.source}</span>
                                    <span className="text-xs font-black text-emerald-600">{s.avg_objectivity > 0 ? (s.avg_objectivity * 100).toFixed(0) + '% Objektivnost' : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="border border-border p-6 bg-red-50/50 dark:bg-red-950/10 border-l-4 border-l-red-500">
                        <h4 className="sidebar-label !border-red-500 !text-red-700 dark:!text-red-400 mb-6">Najnizok senzacionalizam</h4>
                        <div className="flex flex-col gap-4">
                            {[...pulseLeaders].sort((a,b) => a.avg_sensationalism - b.avg_sensationalism).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center group">
                                    <span className="font-bold text-sm group-hover:text-red-600 transition-colors">{s.source}</span>
                                    <span className="text-xs font-black text-red-600">{s.avg_sensationalism > 0 ? (s.avg_sensationalism * 100).toFixed(0) + '% Senzacija' : '–'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {(!loading || pulseLeaders.length > 0) && (
                <section id="leaderboard" className={`mt-24 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                    <div className="section-heading-row masthead-double-rule mb-8">
                        <h2 className="section-title-italic !mb-0">Rang na redakcii (24c)</h2>
                    </div>
                    <div className="broadsheet-table-wrapper">
                        <table className="broadsheet-table">
                            <thead>
                                <tr>
                                    <th title="Medium ili izvor na informacii">REDAKCIJA</th>
                                    <th title="Prosecen sentiment (pozitiven, negativen, neutralen)">TON</th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>OBJEKTIVNOST</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[10px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal">
                                                Faktičko izveštavanje bez subjektivnih komentara.
                                            </div>
                                        </div>
                                    </th>
                                    <th className="text-right">
                                        <div className="flex items-center justify-end gap-1 group cursor-help">
                                            <span>SENZACIONALIZAM</span>
                                            <Info size={10} className="opacity-40 group-hover:opacity-100" />
                                            <div className="absolute hidden group-hover:block bg-foreground text-background text-[10px] p-2 rounded shadow-xl mt-12 z-50 w-48 font-sans normal-case tracking-normal">
                                                Upotreba na emotivno nabien ili preuvelicen recnik.
                                            </div>
                                        </div>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {pulseLeaders.map((row: PulseRow) => (
                                    <tr key={row.source} className="hover:bg-secondary/5 transition-colors">
                                        <td>
                                            <div className="table-source">
                                                <strong>{row.source}</strong>
                                                <span>{row.cluster_count} temi</span>
                                            </div>
                                        </td>
                                        <td><span className={`tone-label ${getSentimentIcon(row.avg_sentiment).color}`} title={getSentimentIcon(row.avg_sentiment).title}>{getSentimentIcon(row.avg_sentiment).icon}</span></td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="stat-bar shadow-inner"><div style={{ width: `${row.avg_objectivity * 100}%` }}></div></div>
                                                <span className="stat-num">{formatStat(row.avg_objectivity)}</span>
                                                <div className="w-8 flex items-center justify-center">
                                                    {row.objectivity_delta !== undefined && row.objectivity_delta !== 0 && (
                                                        <span 
                                                            className={`text-[8px] font-black ${row.objectivity_delta > 0 ? 'text-emerald-500' : 'text-nyt-red'}`}
                                                            title={`Promena vo odnos na 7-dneven prosek: ${(row.objectivity_delta * 100).toFixed(1)}%`}
                                                        >
                                                            {row.objectivity_delta > 0 ? '▲' : '▼'}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="stat-bar bar-red shadow-inner"><div style={{ width: `${row.avg_sensationalism * 100}%` }}></div></div>
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
