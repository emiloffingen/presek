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
        <>
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

            <div className={`pulse-stats-grid mb-24 transition-opacity duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}>
                <div className="pulse-card">
                    <p className="card-label"><Activity size={12}/> ИНФОРМАТИВЕН РИТАМ</p>
                    <p className="card-value">{globalPulse?.last_24h?.toLocaleString('mk-MK') || 0}</p>
                    <div className="card-sparkline">
                        {velocityData.slice(-12).map((v: any, i: number) => {
                            const maxVelocity = Math.max(1, ...velocityData.map((d: any) => d.n || 0));
                            const height = Math.max(15, ((v.n || 0) / maxVelocity) * 100);
                            return <div key={i} className="bar" style={{ height: `${height}%` }}></div>
                        })}
                    </div>
                </div>

                <div className="pulse-card">
                    <p className="card-label"><ShieldCheck size={12}/> ДИВЕРЗИТЕТ НА СТАВОВИ</p>
                    <p className="card-value">{intelligence.pluralism?.pluralism_pct || 0}%</p>
                    <p className="card-note">{intelligence.pluralism?.high_consensus_pct}% висок консензус</p>
                </div>

                <div className="pulse-card">
                    <p className="card-label"><Globe size={12}/> СВЕТОТ КАЈ НАС</p>
                    <p className="card-value">{intelligence.international_share_pct || 0}%</p>
                    <p className="card-note">Вести од меѓународни извори</p>
                </div>

                <div className="pulse-card">
                    <p className="card-label"><Zap size={12}/> ТРЕНДИНГ {category && <span className="text-[8px] opacity-60">ВО {category}</span>}</p>
                    <div className="card-list">
                        {topEntities.slice(0, 3).map((e: any, i: number) => (
                            <div key={i} className="list-item">
                                <span className="truncate">{e.name}</span>
                                <strong className="text-nyt-accent">+{e.total_mentions}</strong>
                            </div>
                        ))}
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
                                            className="p-4 border border-border bg-card hover:border-nyt-accent transition-all group"
                                        >
                                            <span className="text-[9px] font-black uppercase text-nyt-accent block mb-2">{getTypeLabel(ent.type)}</span>
                                            <h3 className="font-serif font-bold text-base leading-tight group-hover:text-nyt-accent">{ent.name}</h3>
                                            <div className="mt-3 flex items-center justify-between">
                                                <span className="text-[10px] font-bold uppercase text-muted-foreground">+{ent.total_mentions} теми денес</span>
                                                <div className={`w-2 h-2 rounded-full ${ent.sentiment_score > 0.1 ? 'bg-green-500' : ent.sentiment_score < -0.1 ? 'bg-nyt-red' : 'bg-muted'}`}></div>
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
        </>
    );
}
