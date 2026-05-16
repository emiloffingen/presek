import React, { useState, useEffect } from 'react';
import { apiBaseUrl } from '../../lib/apiBase';
import { Activity, Zap, Info } from 'lucide-react';

interface ActivitySource {
    source: string;
    activity_score: number;
}

export default function PulseHeatmapIsland({ lang = 'sr' }: { lang?: string }) {
    const [data, setData] = useState<ActivitySource[]>([]);
    const [loading, setLoading] = useState(true);
    const API_URL = apiBaseUrl();

    useEffect(() => {
        async function fetchData() {
            try {
                const res = await fetch(`${API_URL}/intelligence/live-map?lang=${lang}`);
                const json = await res.json();
                if (json.status === 'success') {
                    setData(json.data || []);
                }
            } catch (err) {
                console.error("Heatmap fetch error:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
        const interval = setInterval(fetchData, 30000); // Update every 30s
        return () => clearInterval(interval);
    }, [lang]);

    if (loading) return <div className="h-64 animate-pulse bg-secondary/10 rounded-xl" />;

    const maxScore = Math.max(1, ...data.map(d => d.activity_score));
    const isMK = lang === 'mk';

    return (
        <section className="pulse-heatmap-module mb-16">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <Activity size={18} className="text-nyt-accent" />
                    <h3 className="font-bold text-lg uppercase tracking-tighter">
                        {isMK ? 'Активност на медиумите' : 'Aktivnost medija'}
                    </h3>
                </div>
                <div className="flex items-center gap-2 text-[10px] font-black uppercase text-muted-foreground">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    {isMK ? 'Во живо (24ч)' : 'Uživo (24h)'}
                </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {data.slice(0, 24).map((item) => {
                    const intensity = (item.activity_score / maxScore);
                    return (
                        <div 
                            key={item.source}
                            className="relative group p-4 border border-border bg-card hover:border-nyt-accent transition-all overflow-hidden"
                            style={{
                                boxShadow: intensity > 0.7 ? `0 0 15px rgba(185, 28, 28, ${intensity * 0.1})` : 'none'
                            }}
                        >
                            <div 
                                className="absolute inset-0 opacity-5 pointer-events-none transition-opacity group-hover:opacity-10"
                                style={{ background: intensity > 0.5 ? 'var(--nyt-red)' : 'var(--nyt-accent)' }}
                            />
                            
                            <div className="relative z-10">
                                <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">
                                    {item.source}
                                </p>
                                <div className="flex items-end justify-between">
                                    <span className="text-xl font-black tabular-nums">
                                        {item.activity_score}
                                    </span>
                                    <div className="flex gap-0.5 mb-1">
                                        {[1, 2, 3].map(i => (
                                            <div 
                                                key={i}
                                                className={`w-1 h-3 rounded-full ${i <= Math.ceil(intensity * 3) ? 'bg-nyt-accent' : 'bg-secondary'}`}
                                                style={{ 
                                                    animationDelay: `${i * 0.1}s`,
                                                    animation: intensity > 0.8 ? 'pulse 1.5s infinite' : 'none'
                                                }}
                                            />
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
            
            <div className="mt-4 flex items-center gap-2 text-[9px] font-bold text-muted-foreground opacity-60 uppercase">
                <Info size={10} />
                {isMK ? 'Резултатот ја претставува тежината на објавите и фреквенцијата во последните 24 часа.' : 'Rezultat predstavlja težinu objava i frekvenciju u poslednjih 24 časa.'}
            </div>
        </section>
    );
}
