import React, { useState, useEffect, useMemo } from 'react';
import { Activity, Zap, ShieldCheck, Globe, Timer, Loader2, BarChart3, TrendingUp, Users } from 'lucide-react';
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
}

interface PulseClientContainerProps {
    initialGlobalPulse: any;
    initialPulseData: PulseRow[];
    categories: string[];
    ssrFailed?: boolean;
}

export default function PulseClientContainer({ initialGlobalPulse, initialPulseData, categories, ssrFailed }: PulseClientContainerProps) {
    const [category, setCategory] = useState<string | null>(null);
    const [globalPulse, setGlobalPulse] = useState(initialGlobalPulse);
    const [pulseData, setPulseData] = useState<PulseRow[]>(initialPulseData);
    const [loading, setLoading] = useState(false);
    const API_URL = apiBaseUrl();

    useEffect(() => {
        // Fetch if we don't have data, if SSR failed, or if the category has changed.
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
    const pulseLeaders = pulseData.slice(0, 15);

    function getSentimentLabel(score: number) {
        if (score > 0.2) return { label: 'Позитивен', color: 'text-green-600' };
        if (score < -0.2) return { label: 'Критичен', color: 'text-nyt-red' };
        return { label: 'Неутрален', color: 'text-muted-foreground' };
    }

    function formatStat(val: number) {
        return (val * 100).toFixed(0) + '%';
    }

    function getTypeLabel(type: string) {
        const map: Record<string, string> = {
            'PER': 'Личност',
            'ORG': 'Организација',
            'LOC': 'Локација',
            'ENTITY': 'Субјект'
        };
        return map[type] || 'Субјект';
    }

    return (
        <div className="pulse-client-container w-full max-w-full overflow-x-hidden">
            {/* Category Filter Bar */}
            <nav className="flex items-center gap-2 mb-12 border-b border-border pb-4 overflow-x-auto hide-scrollbar sticky top-[72px] bg-background/80 backdrop-blur-md z-30 py-2">
                <button 
                    onClick={() => setCategory(null)}
                    className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all whitespace-nowrap ${category === null ? 'bg-nyt-accent text-white' : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'}`}
                >
                    СИТЕ КАТЕГОРИИ
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
                <div className="pulse-card" title="Вкупен број на обработени објави во последните 24 часа.">
                    <p className="card-label"><Activity size={12}/> ИНФОРМАТИВЕН РИТАМ</p>
                    <p className="card-value">{globalPulse?.last_24h?.toLocaleString('mk-MK') || 0}</p>
                    <div className="card-sparkline">
                        {velocityData.length > 0 ? velocityData.slice(-12).map((v: any, i: number) => {
                            const maxVelocity = Math.max(1, ...velocityData.map((d: any) => d.n || 0));
                            const height = Math.max(15, ((v.n || 0) / maxVelocity) * 100);
                            return <div key={i} className="bar" style={{ height: `${height}%` }}></div>
                        }) : (
                            <div className="w-full h-px bg-border opacity-20 self-center"></div>
                        )}
                    </div>
                </div>

                <div className="pulse-card border-t-4 border-t-nyt-accent" title="Процент на теми кои се покриени од повеќе различни извори (покажува медиумски фокус).">
                    <p className="card-label !text-nyt-accent"><ShieldCheck size={12}/> ПЛУРАЛИЗАМ</p>
                    <p className="card-value">{intelligence.pluralism?.pluralism_pct || 0}%</p>
                    <p className="card-note">{(intelligence.pluralism?.pluralism_pct || 0) > 0 ? `${intelligence.pluralism?.high_consensus_pct}% медиумски консензус` : 'Системот анализира нови кластери'}</p>
                </div>

                <div className="pulse-card" title="Процент на меѓународни извори што известуваат.">
                    <p className="card-label"><Globe size={12}/> СВЕТОТ КАЈ НАС</p>
                    <p className="card-value">{intelligence.international_share_pct || 0}%</p>
                    <p className="card-note">Вести од меѓународни извори</p>
                </div>

                <div className="pulse-card" title="Субјекти кои моментално се најзастапени во вестите.">
                    <p className="card-label"><Zap size={12}/> ТРЕНДИНГ {category && <span className="text-[8px] opacity-60">ВО {category}</span>}</p>
                    <div className="card-list">
                        {topEntities.length > 0 ? topEntities.slice(0, 3).map((e: any, i: number) => (
                            <div key={i} className="list-item">
                                <span className="truncate">{e.name}</span>
                                <strong className="text-nyt-accent">+{e.total_mentions}</strong>
                            </div>
                        )) : (
                            <p className="text-[10px] text-muted-foreground italic py-2">Нема доволно податоци за трендови</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Quick Insights Deck */}
            <div className="bg-secondary/10 border border-border p-6 rounded-lg mb-20 flex flex-col md:flex-row gap-8 items-center">
                <div className="flex-1">
                    <h3 className="text-[11px] font-black uppercase tracking-widest text-nyt-accent mb-2">Клучни Увиди</h3>
                    <p className="font-serif italic text-lg leading-snug">
                        {intelligence.pluralism?.pluralism_pct > 50 
                            ? "Забележан е висок степен на медиумски консензус кај водечките стории денес."
                            : "Низок плурализам: темите се обработуваат со специфични, дивергентни агли."
                        }
                    </p>
                </div>
                <div className="flex-1 grid grid-cols-2 gap-4 border-l border-border pl-8">
                    <div>
                        <span className="block text-[9px] font-black uppercase text-muted-foreground">Транспарентност</span>
                        <span className="text-lg font-black">{intelligence.synthesis_transparency?.systemic_ratio || 0}%</span>
                    </div>
                    <div>
                        <span className="block text-[9px] font-black uppercase text-muted-foreground">Стабилност</span>
                        <span className="text-lg font-black text-emerald-600">Оптимална</span>
                    </div>
                </div>
            </div>

            <div className="broadsheet-grid">
                <div className="broadsheet-main">
                    {/* 1. HORIZON ANALYSIS */}
                    <section className="mb-16">
                        <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                            <h2 className="section-title-italic !mb-0 text-3xl">Редакциски Хоризонт</h2>
                            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                                <BarChart3 size={12} /> Аналитика по теми
                            </div>
                        </div>
                        <PulseLandscapeIsland data={pulseData} loading={loading} />
                    </section>

                    {/* 2. KEY ACTORS GRID */}
                    <section className="mb-20">
                        <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                            <h2 className="section-title-italic !mb-0 text-3xl">Клучни Актори</h2>
                            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                                <Users size={12} /> во фокус
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
                                            <span className="text-xl">{ent.sentiment_score > 0.1 ? '😊' : ent.sentiment_score < -0.1 ? '😤' : '😐'}</span>
                                        </div>
                                        <h3 className="font-serif font-black text-xl leading-tight group-hover:text-nyt-accent mb-6">{ent.name}</h3>
                                        <div className="mt-auto pt-4 border-t border-border/40 flex items-center justify-between">
                                            <div className="flex flex-col">
                                                <span className="text-[10px] font-bold text-muted-foreground uppercase">Споменувања</span>
                                                <span className="text-xl font-black tabular-nums">{ent.total_mentions}</span>
                                            </div>
                                            <div className={`text-[10px] font-black uppercase tracking-tighter ${ent.sentiment_score > 0.1 ? 'text-green-600' : ent.sentiment_score < -0.1 ? 'text-red-600' : 'text-muted-foreground'}`}>
                                                {ent.sentiment_score > 0.1 ? 'Позитивен' : ent.sentiment_score < -0.1 ? 'Критичен' : 'Неутрален'}
                                            </div>
                                        </div>
                                    </a>
                                ))}
                            </div>
                        ) : (
                            <div className="py-20 text-center border border-dashed border-border rounded-2xl bg-secondary/5">
                                <Users className="mx-auto mb-4 opacity-10" size={48} />
                                <p className="font-serif italic text-muted-foreground text-lg">Системот анализира нови актери во оваа категорија...</p>
                            </div>
                        )}
                    </section>
                </div>

                <aside className="broadsheet-rail">
                    <section className="rail-block">
                        <p className="rail-kicker">Методологија</p>
                        <h3 className="rail-title italic font-serif text-lg">Уреднички Алгоритам</h3>
                        <p className="rail-text">
                            Информациите во овој индекс се генерираат преку автоматска обработка на природниот јазик (NLP) на сите вклучени македонски извори за изминатите 24 часа.
                        </p>
                    </section>

                    <div className="sidebar-module mt-12">
                        <h4 className="sidebar-label">СПОРЕДБА НА ИЗВОРИ</h4>
                        <div className="mt-4">
                            <SourceComparisonIsland allSources={pulseData.map((r: PulseRow) => r.source)} />
                        </div>
                    </div>
                </aside>
            </div>

            {/* Transparency Scoreboard */}
            <section className="mt-20">
                <h2 className="section-title-italic mb-8 masthead-double-rule">Индекс на Транспарентност</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="border border-border p-6 bg-emerald-50/50 dark:bg-emerald-950/10">
                        <h4 className="sidebar-label !border-emerald-500 !text-emerald-700 dark:!text-emerald-400 mb-6">Најобјективни извори (24ч)</h4>
                        <div className="flex flex-col gap-4">
                            {[...pulseLeaders].sort((a,b) => b.avg_objectivity - a.avg_objectivity).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center">
                                    <span className="font-bold text-sm">{s.source}</span>
                                    <span className="text-xs font-black text-emerald-600">{(s.avg_objectivity * 100).toFixed(0)}% Објективност</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="border border-border p-6 bg-red-50/50 dark:bg-red-950/10">
                        <h4 className="sidebar-label !border-red-500 !text-red-700 dark:!text-red-400 mb-6">Најнизок сензационализам</h4>
                        <div className="flex flex-col gap-4">
                            {[...pulseLeaders].sort((a,b) => a.avg_sensationalism - b.avg_sensationalism).slice(0, 3).map(s => (
                                <div key={s.source} className="flex justify-between items-center">
                                    <span className="font-bold text-sm">{s.source}</span>
                                    <span className="text-xs font-black text-red-600">{(s.avg_sensationalism * 100).toFixed(0)}% Сензација</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {(!loading || pulseLeaders.length > 0) && (
                <section className={`mt-20 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                    <h2 className="section-title-italic mb-8 masthead-double-rule">Ранг на редакции (24ч)</h2>
                    <div className="broadsheet-table-wrapper">
                        <table className="broadsheet-table">
                            <thead>
                                <tr>
                                    <th title="Медиум или извор на информации">РЕДАКЦИЈА</th>
                                    <th title="Просечен сентимент (позитивен, негативен, неутрален)">ТОН</th>
                                    <th className="text-right" title="Процент на фактичко известување без субјективни коментари">ОБЈЕКТИВНОСТ</th>
                                    <th className="text-right" title="Процент на емотивно набиен или преувеличен речник">СЕНЗАЦИОНАЛИЗАМ</th>
                                </tr>
                            </thead>
                            <tbody>
                                {pulseLeaders.map((row: PulseRow) => (
                                    <tr key={row.source}>
                                        <td>
                                            <div className="table-source">
                                                <strong>{row.source}</strong>
                                                <span>{row.cluster_count} теми</span>
                                            </div>
                                        </td>
                                        <td><span className={`tone-label ${getSentimentLabel(row.avg_sentiment).color}`}>{getSentimentLabel(row.avg_sentiment).label}</span></td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="stat-bar"><div style={{ width: `${row.avg_objectivity * 100}%` }}></div></div>
                                                <span className="stat-num">{formatStat(row.avg_objectivity)}</span>
                                            </div>
                                        </td>
                                        <td className="text-right">
                                            <div className="stat-row">
                                                <div className="stat-bar bar-red"><div style={{ width: `${row.avg_sensationalism * 100}%` }}></div></div>
                                                <span className="stat-num text-nyt-red">{formatStat(row.avg_sensationalism)}</span>
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
