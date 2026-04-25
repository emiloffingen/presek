import React, { useMemo } from 'react';
import { ShieldCheck, Zap } from 'lucide-react';

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

const PulseLandscapeIsland: React.FC<{ data: PulseRow[] }> = ({ data }) => {
    if (!data || data.length === 0) return null;

    // Filter to top sources for clarity in the map
    const plotData = useMemo(() => {
        return data
            .slice(0, 30)
            .map((item, idx) => {
                // Base positions
                const xBase = item.avg_objectivity * 100;
                const yBase = item.avg_sensationalism * 100;
                
                // Deterministic jitter based on index to prevent overlap
                // while keeping the point close to its real value
                const jitterX = ((idx % 3) - 1) * 2.5; 
                const jitterY = (((idx * 7) % 3) - 1) * 2.5;

                return {
                    ...item,
                    x: Math.max(5, Math.min(95, xBase + jitterX)),
                    y: Math.max(5, Math.min(95, yBase + jitterY))
                };
            });
    }, [data]);

    return (
        <section className="mb-12 border border-border rounded-[1.25rem] bg-card p-6 md:p-8 overflow-hidden">
            <div className="relative w-full aspect-square md:aspect-[16/9] border-2 border-border/50 bg-secondary/10 rounded-lg p-4 md:p-8">
                {/* Quadrant Labels */}
                <div className="absolute top-4 left-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-nyt-red/80 bg-background/40 px-2 py-1 rounded">Субјективни & Сензационални</div>
                <div className="absolute top-4 right-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-nyt-accent/80 bg-background/40 px-2 py-1 rounded">Објективни & Динамични</div>
                <div className="absolute bottom-4 left-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-muted-foreground/80 bg-background/40 px-2 py-1 rounded">Традиционални & Статични</div>
                <div className="absolute bottom-4 right-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-emerald-600/80 bg-background/40 px-2 py-1 rounded">Прецизни & Аналитички</div>

                {/* Axes */}
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border/40 dashed"></div>
                <div className="absolute top-1/2 left-0 right-0 h-px bg-border/40 dashed"></div>

                {/* Axis Labels */}
                <div className="absolute bottom-[-25px] left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Објективност →</div>
                <div className="absolute left-[-40px] top-1/2 -rotate-90 -translate-y-1/2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Сензационализам →</div>

                {/* Plot Area */}
                <div className="relative w-full h-full">
                    {plotData.map((source) => (
                        <div 
                            key={source.source}
                            className="absolute group transition-all hover:z-50 cursor-help"
                            style={{ 
                                left: `${source.x}%`, 
                                bottom: `${source.y}%`,
                                transform: 'translate(-50%, 50%)'
                            }}
                        >
                            <div className={`
                                flex items-center justify-center
                                rounded-full border-2 shadow-sm transition-all group-hover:scale-125
                                ${source.trust_label === 'Висока доверба' ? 'bg-nyt-accent border-blue-200' : 'bg-background border-border'}
                            `}
                            style={{
                                width: source.trust_label === 'Висока доверба' ? '12px' : '8px',
                                height: source.trust_label === 'Висока доверба' ? '12px' : '8px',
                            }}>
                            </div>

                            {/* Label */}
                            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 px-1.5 py-0.5 bg-background/80 backdrop-blur-sm border border-border rounded whitespace-nowrap opacity-40 group-hover:opacity-100 transition-opacity">
                                <span className={`text-[9px] font-black uppercase tracking-tight ${source.trust_label === 'Висока доверба' ? 'text-nyt-accent' : 'text-foreground'}`}>
                                    {source.source}
                                </span>
                            </div>

                            {/* Tooltip */}
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 bg-foreground text-background p-3 rounded-lg shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-all z-50">
                                <p className="text-[11px] font-black uppercase tracking-widest border-b border-background/20 pb-1 mb-2 flex items-center justify-between">
                                    {source.source}
                                    {source.trust_label === 'Висока доверба' && <ShieldCheck size={10} className="text-blue-400" />}
                                </p>
                                <div className="space-y-1.5">
                                    <div className="flex justify-between text-[10px]">
                                        <span>Објективност:</span>
                                        <span className="font-bold">{(source.avg_objectivity * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="flex justify-between text-[10px]">
                                        <span>Сензационализам:</span>
                                        <span className="font-bold">{(source.avg_sensationalism * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="flex justify-between text-[10px]">
                                        <span>Брзина (Прв на вест):</span>
                                        <span className="font-bold text-nyt-accent">{source.first_report_count}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-nyt-accent"></div>
                    <span className="text-[10px] font-bold uppercase text-muted-foreground">Висока доверба</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-background border border-border"></div>
                    <span className="text-[10px] font-bold uppercase text-muted-foreground">Следен извор</span>
                </div>
            </div>
        </section>
    );
};

export default PulseLandscapeIsland;