import React from 'react';
import { Target, MessageSquare, ShieldCheck, AlertCircle } from 'lucide-react';

interface Narrative {
    text: string;
    sentiment: 'POZITIVAN' | 'NEUTRALAN' | 'KRITIČAN' | 'КРИТИЧЕН' | 'ПОЗИТИВЕН' | 'НЕУТРАЛЕН';
}

interface Props {
    narratives: Narrative[];
    lang?: string;
}

export default function NarrativeList({ narratives, lang = 'sr' }: Props) {
    const isMK = lang === 'mk';

    if (!narratives || narratives.length === 0) return null;

    const getSentimentColor = (sentiment: string) => {
        const s = sentiment.toUpperCase();
        if (s.includes('POZITIVAN') || s.includes('ПОЗИТИВЕН')) return 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20';
        if (s.includes('KRITIČAN') || s.includes('КРИТИЧЕН')) return 'bg-nyt-red/10 text-nyt-red border-nyt-red/20';
        return 'bg-secondary/50 text-muted-foreground border-border';
    };

    const getSentimentLabel = (sentiment: string) => {
        const s = sentiment.toUpperCase();
        if (s.includes('POZITIVAN') || s.includes('ПОЗИТИВЕН')) return isMK ? 'ПОЗИТИВЕН' : 'POZITIVAN';
        if (s.includes('KRITIČAN') || s.includes('КРИТИЧЕН')) return isMK ? 'КРИТИЧЕН' : 'KRITIČAN';
        return isMK ? 'НЕУТРАЛЕН' : 'NEUTRALAN';
    };

    return (
        <section className="narrative-highlights mb-20 animate-rise">
            <div className="flex items-center gap-[var(--grid-gap)] mb-8">
                <Target size={20} className="text-nyt-accent" />
                <h2 className="font-bold text-lg uppercase tracking-tighter">
                    {isMK ? 'Клучни Наративи' : 'Ključni Narativi'}
                </h2>
                <div className="h-px flex-1 bg-border/40 ml-2" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-[var(--grid-gap)]">
                {narratives.map((nar, i) => (
                    <div key={i} className="p-6 border border-border bg-card rounded-xl shadow-sm hover:shadow-md transition-all flex flex-col group h-full">
                        <div className="flex items-center justify-between mb-4">
                            <span className={`text-[8px] font-black px-2 py-0.5 rounded border ${getSentimentColor(nar.sentiment)}`}>
                                {getSentimentLabel(nar.sentiment)}
                            </span>
                            <MessageSquare size={14} className="text-muted-foreground opacity-20 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <p className="font-serif italic text-lg leading-snug flex-1">
                            "{nar.text}"
                        </p>
                        <div className="mt-6 pt-4 border-t border-border/40 flex items-center gap-[var(--grid-gap)] text-[9px] font-black uppercase text-muted-foreground opacity-40">
                            <ShieldCheck size={10} />
                            {isMK ? 'СИСТЕМСКА ВЕРИФИКАЦИЈА' : 'SISTEMSKA VERIFIKACIJA'}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}
