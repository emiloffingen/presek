import React, { useMemo } from 'react';
import { ShieldCheck, Newspaper, ArrowUpRight } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { pulse } from '../i18n/namespaces/pulse';
import { sources } from '../i18n/namespaces/sources';

interface PulseRow {
    source: string;
    avg_sentiment: number;
    avg_objectivity: number;
    avg_sensationalism: number;
    cluster_count: number;
    first_report_count: number;
    trust_label?: string;
    effective_weight?: number;
    latest_headline?: string;
    latest_cluster_id?: string;
}

const PulseLandscapeIsland: React.FC<{ data: PulseRow[], loading?: boolean, lang?: string, onSourceClick?: (s: string) => void }> = ({ data, loading = false, lang = 'sr', onSourceClick }) => {
    const locale = lang === 'mk' ? 'mk' : 'sr';
    const t = useClientTranslations(locale, pulse, sources);
    const highTrustLabel = t('sources.high_trust');

    const plotData = useMemo(() => {
        if (!data || data.length === 0) return [];

        const topData = data.slice(0, 35);
        const objs = topData.map(d => d.avg_objectivity);
        const sens = topData.map(d => d.avg_sensationalism);
        const minObj = Math.min(...objs);
        const maxObj = Math.max(...objs);
        const minSens = Math.min(...sens);
        const maxSens = Math.max(...sens);
        const rangeObj = (maxObj - minObj) || 1;
        const rangeSens = (maxSens - minSens) || 1;

        return topData.map((item, idx) => {
            const xNorm = 15 + ((item.avg_objectivity - minObj) / rangeObj) * 70;
            const yNorm = 15 + ((item.avg_sensationalism - minSens) / rangeSens) * 70;
            const jitterX = ((idx % 3) - 1) * 2.2;
            const jitterY = (((idx * 7) % 3) - 1) * 2.2;

            return {
                ...item,
                x: Math.max(5, Math.min(95, xNorm + jitterX)),
                y: Math.max(5, Math.min(95, yNorm + jitterY))
            };
        });
    }, [data]);

    if (loading) {
        return (
            <div className="mb-12 border border-border rounded-[1.25rem] bg-card p-6 md:p-8 animate-pulse overflow-hidden">
                <div className="relative w-full aspect-square md:aspect-[16/9] border-2 border-border/30 bg-secondary/5 rounded-lg p-4 md:p-8">
                     <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border/20 dashed"></div>
                     <div className="absolute top-1/2 left-0 right-0 h-px bg-border/20 dashed"></div>
                     <div className="w-full h-full flex items-center justify-center">
                        <span className="font-serif italic text-muted-foreground opacity-50">
                            {t('pulse.landscape_loading')}
                        </span>
                     </div>
                </div>
            </div>
        );
    }
    if (!data || data.length === 0) return null;

    return (
        <section className="mb-12 border border-border rounded-[1.25rem] bg-card p-6 md:p-8 overflow-hidden shadow-sm">
            <div className="relative w-full aspect-square md:aspect-[16/9] border-2 border-border/50 bg-secondary/10 rounded-lg p-4 md:p-8">
                <div className="absolute top-4 left-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-nyt-red/80 bg-background/95 px-2.5 py-1.5 rounded border border-nyt-red/10 shadow-sm z-10">
                    {t('pulse.landscape_quad_subj_sens')}
                </div>
                <div className="absolute top-4 right-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-presek-mark/80 bg-background/95 px-2.5 py-1.5 rounded border border-presek-mark/10 shadow-sm z-10">
                    {t('pulse.landscape_quad_obj_dyn')}
                </div>
                <div className="absolute bottom-4 left-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-muted-foreground/80 bg-background/95 px-2.5 py-1.5 rounded border border-border/40 shadow-sm z-10">
                    {t('pulse.landscape_quad_trad_stat')}
                </div>
                <div className="absolute bottom-4 right-4 text-[10px] md:text-[11px] font-black uppercase tracking-widest text-emerald-600/80 bg-background/95 px-2.5 py-1.5 rounded border border-emerald-600/10 shadow-sm z-10">
                    {t('pulse.landscape_quad_prec_analyt')}
                </div>

                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-foreground/10 dashed"></div>
                <div className="absolute top-1/2 left-0 right-0 h-px bg-foreground/10 dashed"></div>

                <div className="absolute bottom-[-28px] left-1/2 -translate-x-1/2 text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">
                    {t('pulse.landscape_axis_objectivity')} →
                </div>
                <div className="absolute left-[-45px] top-1/2 -rotate-90 -translate-y-1/2 text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">
                    {t('pulse.landscape_axis_sensation')} →
                </div>

                <div className="relative w-full h-full">
                    {plotData.map((source) => {
                        const isHighTrust = source.trust_label === highTrustLabel;
                        return (
                        <div
                            key={source.source}
                            onClick={() => onSourceClick?.(source.source)}
                            className="absolute group transition-all hover:z-50 cursor-pointer"
                            style={{
                                left: `${source.x}%`,
                                bottom: `${source.y}%`,
                                transform: 'translate(-50%, 50%)'
                            }}
                        >
                            <div className={`
                                flex items-center justify-center
                                rounded-full border-2 shadow-md transition-all group-hover:scale-150 group-hover:shadow-lg
                                ${isHighTrust ? 'bg-presek-mark border-presek-mark/30' : 'bg-background border-border'}
                            `}
                            style={{
                                width: isHighTrust ? '14px' : '10px',
                                height: isHighTrust ? '14px' : '10px',
                            }}>
                                {isHighTrust && <div className="w-1 h-1 bg-white rounded-full"></div>}
                            </div>

                            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1.5 px-2 py-0.5 bg-background/95 border border-border/50 rounded shadow-sm whitespace-nowrap opacity-40 group-hover:opacity-100 group-hover:border-presek-mark/50 transition-all z-20">
                                <span className={`text-[9px] font-black uppercase tracking-tight ${isHighTrust ? 'text-presek-mark' : 'text-foreground'}`}>
                                    {source.source}
                                </span>
                            </div>

                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 w-64 bg-foreground text-background p-4 rounded-xl shadow-2xl pointer-events-none opacity-0 group-hover:opacity-100 transition-all z-50 scale-95 group-hover:scale-100">
                                <div className="flex items-center justify-between border-b border-background/20 pb-2 mb-3">
                                    <p className="text-[12px] font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)] text-background">
                                        {source.source}
                                        {isHighTrust && <ShieldCheck size={11} className="text-blue-400" />}
                                    </p>
                                    <span className="text-[9px] font-bold opacity-60 flex items-center gap-1 text-background">{t('pulse.landscape_focus_label')} <ArrowUpRight size={10}/></span>
                                </div>

                                <div className="space-y-2 mb-4">
                                    <div className="flex justify-between text-[11px]">
                                        <span className="opacity-70 text-background">{t('pulse.landscape_axis_objectivity')}:</span>
                                        <span className="font-black text-background">{(source.avg_objectivity * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="flex justify-between text-[11px]">
                                        <span className="opacity-70 text-background">{t('pulse.landscape_sensationalism')}:</span>
                                        <span className="font-black text-background">{(source.avg_sensationalism * 100).toFixed(0)}%</span>
                                    </div>
                                </div>

                                {source.latest_headline && (
                                    <div className="pt-3 border-t border-background/10">
                                        <p className="text-[9px] font-black uppercase tracking-widest opacity-40 mb-1 flex items-center gap-1 text-background">
                                            <Newspaper size={8} /> {t('pulse.landscape_latest_published')}
                                        </p>
                                        <p className="font-serif italic text-xs leading-snug line-clamp-2 opacity-90 text-background">
                                            "{source.latest_headline}"
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>
                        );
                    })}
                </div>
            </div>

            <div className="mt-12 flex flex-wrap gap-[var(--grid-gap)] items-center justify-center md:justify-start border-t border-border pt-6">
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <div className="w-3.5 h-3.5 rounded-full bg-presek-mark shadow-sm border border-presek-mark/30"></div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{highTrustLabel}</span>
                </div>
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <div className="w-2.5 h-2.5 rounded-full bg-background border-2 border-border shadow-sm"></div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{t('pulse.landscape_other_sources')}</span>
                </div>
                <div className="hidden md:block ml-auto text-[9px] font-bold italic opacity-40 uppercase tracking-tighter">
                    {t('pulse.landscape_data_window')}
                </div>
            </div>
        </section>
    );
};

export default PulseLandscapeIsland;
