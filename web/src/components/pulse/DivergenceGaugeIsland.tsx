import React from 'react';
import { Gauge, HelpCircle } from 'lucide-react';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { pulse } from '../../i18n/namespaces/pulse';

interface DivergenceProps {
    pluralism_pct: number;
    high_consensus_pct: number;
    lang?: string;
}

export default function DivergenceGaugeIsland({ pluralism_pct, high_consensus_pct, lang = 'sr' }: DivergenceProps) {
    const locale = lang === 'mk' ? 'mk' : 'sr';
    const t = useClientTranslations(locale, pulse);
    const divergence = pluralism_pct || 0;
    const rotation = (divergence / 100) * 180 - 90;

    const getStatus = (score: number) => {
        if (score > 70) return {
            label: t('pulse.divergence_high_pluralism'),
            color: 'text-emerald-500',
            desc: t('pulse.divergence_high_desc'),
        };
        if (score > 30) return {
            label: t('pulse.divergence_balanced'),
            color: 'text-presek-mark',
            desc: t('pulse.divergence_balanced_desc'),
        };
        return {
            label: t('pulse.divergence_convergence'),
            color: 'text-nyt-red',
            desc: t('pulse.divergence_convergence_desc'),
        };
    };

    const status = getStatus(divergence);

    return (
        <div className="bg-card border border-border p-6 rounded-none relative overflow-hidden h-full flex flex-col">
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <Gauge size={18} className="text-muted-foreground" />
                    <h3 className="font-bold text-sm uppercase tracking-tighter">
                        {t('pulse.divergence_title')}
                    </h3>
                </div>
                <div className="group relative">
                    <HelpCircle size={14} className="text-muted-foreground opacity-40 cursor-help" />
                    <div className="absolute hidden group-hover:block right-0 bg-foreground text-background text-[10px] p-3 rounded-none border border-background/20 z-50 w-64 font-sans leading-relaxed">
                        {t('pulse.divergence_tooltip')}
                    </div>
                </div>
            </div>

            <div className="relative flex-1 flex flex-col items-center justify-center pt-4">
                <div className="relative w-48 h-24 overflow-hidden">
                    <div className="absolute top-0 left-0 w-48 h-48 border-[12px] border-secondary rounded-full" />
                    <div
                        className="absolute top-0 left-0 w-48 h-48 border-[12px] border-transparent border-t-presek-mark border-r-presek-mark rounded-full transition-transform duration-1000 ease-out"
                        style={{ transform: `rotate(${rotation}deg)` }}
                    />
                    <div
                        className="absolute bottom-0 left-1/2 w-1 h-20 bg-foreground origin-bottom -translate-x-1/2 transition-transform duration-1000 ease-out"
                        style={{ transform: `translateX(-50%) rotate(${rotation}deg)` }}
                    >
                        <div className="w-3 h-3 bg-foreground rounded-full absolute -bottom-1.5 -left-1 shadow-lg" />
                    </div>
                </div>

                <div className="text-center mt-6">
                    <p className={`text-xl font-black ${status.color}`}>{divergence}%</p>
                    <p className="text-[10px] font-black uppercase tracking-widest mt-1">{status.label}</p>
                </div>
            </div>

            <div className="mt-8 pt-6 border-t border-border/50">
                <p className="text-xs font-serif italic text-muted-foreground leading-relaxed">
                    {status.desc}
                </p>
                <div className="mt-4 flex items-center justify-between text-[9px] font-black uppercase text-muted-foreground opacity-60">
                    <span>{t('pulse.divergence_focus_label')}: {high_consensus_pct}%</span>
                    <span>{t('pulse.divergence_diversity_label')}: {pluralism_pct}%</span>
                </div>
            </div>
        </div>
    );
}
