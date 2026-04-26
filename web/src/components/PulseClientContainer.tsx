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
}

export default function PulseClientContainer({ initialGlobalPulse, initialPulseData, categories }: PulseClientContainerProps) {
    const [category, setCategory] = useState<string | null>(null);
    const [globalPulse, setGlobalPulse] = useState(initialGlobalPulse);
    const [pulseData, setPulseData] = useState<PulseRow[]>(initialPulseData);
    const [loading, setLoading] = useState(false);
    const API_URL = apiBaseUrl();

    useEffect(() => {
        if (category === null && globalPulse === initialGlobalPulse) return;
        
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
                <div className="pulse-card">
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

                <div className="pulse-card border-t-4 border-t-nyt-accent">
                    <p className="card-label !text-nyt-accent"><ShieldCheck size={12}/> ПЛУРАЛИЗАМ</p>
                    <p className="card-value">{intelligence.pluralism?.pluralism_pct || 0}%</p>
                    <p className="card-note">{(intelligence.pluralism?.pluralism_pct || 0) > 0 ? `${intelligence.pluralism?.high_consensus_pct}% медиумски консензус` : 'Системот анализира нови кластери'}</p>
                </div>

                <div className="pulse-card">
                    <p className="card-label"><Globe size={12}/> СВЕТОТ КАЈ НАС</p>
                    <p className="card-value">{intelligence.international_share_pct || 0}%</p>
                    <p className="card-note">Вести од меѓународни извори</p>
                </div>

                <div className="pulse-card">
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
                    <section className="mb-16">
                        <div className="flex items-center justify-between mb-8 border-b border-border pb-4">
                            <h2 className="section-title-italic !mb-0">Редакциски Хоризонт</h2>
                            {category && <span className="text-[10px] font-black uppercase tracking-widest text-nyt-accent">Филтрирано по: {category}</span>}
                        </div>
                        <PulseLandscapeIsland data={pulseData} loading={loading} />
                    </section>

                    <section className="mb-16">
                        <div className="flex items-center gap-2 mb-8 border-b border-border pb-4">
                            <BarChart3 size={20} className="text-nyt-accent" />
                            <h2 className="font-serif text-2xl font-black italic">Аналитика по теми</h2>
                        </div>
                        
                        <div className={`space-y-12 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                            {/* Trending Entities */}
                            <section>
                                <div className="flex items-center gap-2 mb-6 border-b border-border/50 pb-4">
                                    <TrendingUp size={16} className="text-nyt-accent" />
                                    <h3 className="font-sans text-[10px] font-black uppercase tracking-widest">Клучни актери во фокус</h3>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    {topEntities.map((ent: any) => (
                                        <a 
                                            key={ent.name} 
                                            href={`/subjekt/${encodeURIComponent(ent.name)}`}
                                            className="p-5 border border-border bg-card hover:border-nyt-accent hover:shadow-lg hover:-translate-y-1 transition-all group relative overflow-hidden"
                                        >
                                            <div className="absolute top-0 left-0 w-1 h-full bg-nyt-accent/10 group-hover:bg-nyt-accent transition-colors"></div>
                                            <span className="text-[8px] font-black uppercase text-nyt-accent tracking-widest block mb-2">{getTypeLabel(ent.type)}</span>
                                            <h3 className="font-serif font-black text-lg leading-tight group-hover:text-nyt-accent mb-4">{ent.name}</h3>
                                            <div className="flex items-center justify-between mt-auto">
                                                <div className="flex flex-col">
                                                    <span className="text-[9px] font-black uppercase text-muted-foreground tracking-tight">Експонираност</span>
                                                    <span className="text-xs font-black">+{ent.total_mentions} теми</span>
                                                </div>
                                                <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-black uppercase ${ent.sentiment_score > 0.1 ? 'bg-green-100 text-green-700' : ent.sentiment_score < -0.1 ? 'bg-red-100 text-red-700' : 'bg-secondary text-muted-foreground'}`}>
                                                    {ent.sentiment_score > 0.1 ? 'Позитивен' : ent.sentiment_score < -0.1 ? 'Критичен' : 'Неутрален'}
                                                </div>
                                            </div>
                                        </a>
                                    ))}
                                </div>
                            </section>
                        </div>
                    </section>
                </div>

                <aside className="broadsheet-rail">
                    <section className="rail-block rail-block-featured">
                        <p className="rail-kicker">Фокус</p>
                        <h3 className="rail-title">СУБЈЕКТИ</h3>
                        <div className="rail-tag-cloud">
                            {topEntities.map((e: any) => (
                                <a key={e.name} href={`/?entity=${encodeURIComponent(e.name)}`}>
                                    {e.name}
                                </a>
                            ))}
                        </div>
                    </section>

                    <section className="rail-block">
                        <p className="rail-kicker">Методологија</p>
                        <h3 className="rail-title">ИНТЕЛЕКТ</h3>
                        <p className="rail-text">
                            Податоците се генерираат преку автоматизирана анализа на секој кластер. Нашиот алгоритам го оценува известувањето на секој медиум посебно според објективност, тон и сензационализам.
                        </p>
                    </section>

                    <div className="rail-ad-box">
                        <p className="text-[9px] opacity-50 mb-2 uppercase font-bold">Споредба на извори</p>
                        <SourceComparisonIsland allSources={pulseData.map((r: PulseRow) => r.source)} />
                    </div>
                </aside>
            </div>

            {(!loading || pulseLeaders.length > 0) && (
                <section className={`mt-20 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                    <h2 className="section-title-italic mb-8 masthead-double-rule">Ранг на редакции (24ч)</h2>
                    <div className="broadsheet-table-wrapper">
                        <table className="broadsheet-table">
                            <thead>
                                <tr>
                                    <th>РЕДАКЦИЈА</th>
                                    <th>ТОН</th>
                                    <th className="text-right">ОБЈЕКТИВНОСТ</th>
                                    <th className="text-right">СЕНЗАЦИОНАЛИЗАМ</th>
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
