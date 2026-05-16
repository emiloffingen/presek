import React from 'react';
import { Gauge, ShieldCheck, HelpCircle } from 'lucide-react';

interface DivergenceProps {
    pluralism_pct: number;
    high_consensus_pct: number;
    lang?: string;
}

export default function DivergenceGaugeIsland({ pluralism_pct, high_consensus_pct, lang = 'sr' }: DivergenceProps) {
    const isMK = lang === 'mk';
    
    // Normalize pluralism to a "Divergence" score (0-100)
    // High pluralism = high divergence (many different stories)
    // Low pluralism = low divergence (one dominant story)
    const divergence = pluralism_pct || 0;
    const rotation = (divergence / 100) * 180 - 90; // -90 to 90 degrees

    const getStatus = (score: number) => {
        if (score > 70) return { 
            label: isMK ? 'ВИСОК ПЛУРАЛИЗАМ' : 'VISOK PLURALIZAM', 
            color: 'text-emerald-500',
            desc: isMK ? 'Медиумите известуваат за широк спектар на различни теми.' : 'Mediji izveštavaju o širokom spektru različitih tema.'
        };
        if (score > 30) return { 
            label: isMK ? 'БАЛАНСИРАНО' : 'BALANSIRANO', 
            color: 'text-nyt-accent',
            desc: isMK ? 'Постои рамнотежа меѓу заедничките теми и диверзитетот.' : 'Postoji ravnoteža između zajedničkih tema i diverziteta.'
        };
        return { 
            label: isMK ? 'НАРАТИВНА КОНВЕРГЕНЦИЈА' : 'NARATIVNA KONVERGENCIJA', 
            color: 'text-nyt-red',
            desc: isMK ? 'Повеќето медиуми се фокусирани на иста група настани.' : 'Većina medija je fokusirana na istu grupu događaja.'
        };
    };

    const status = getStatus(divergence);

    return (
        <div className="bg-card border border-border p-6 rounded-xl shadow-sm relative overflow-hidden h-full flex flex-col">
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-2">
                    <Gauge size={18} className="text-muted-foreground" />
                    <h3 className="font-bold text-sm uppercase tracking-tighter">
                        {isMK ? 'Мерач на диверзитет' : 'Merač diverziteta'}
                    </h3>
                </div>
                <div className="group relative">
                    <HelpCircle size={14} className="text-muted-foreground opacity-40 cursor-help" />
                    <div className="absolute hidden group-hover:block right-0 bg-foreground text-background text-[10px] p-3 rounded-lg shadow-2xl z-50 w-64 font-sans leading-relaxed">
                        {isMK 
                          ? 'Овој мерач ја следи "распрснатоста" на медиумскиот интерес. Колку е поголем плурализмот, толку помалку медиумите го следат истиот наратив.' 
                          : 'Ovaj merač prati "raspršenost" medijskog interesa. Što je veći pluralizam, to manje mediji prate isti narativ.'}
                    </div>
                </div>
            </div>

            <div className="relative flex-1 flex flex-col items-center justify-center pt-4">
                {/* Semi-circle Gauge */}
                <div className="relative w-48 h-24 overflow-hidden">
                    <div className="absolute top-0 left-0 w-48 h-48 border-[12px] border-secondary rounded-full" />
                    <div 
                        className={`absolute top-0 left-0 w-48 h-48 border-[12px] border-transparent border-t-nyt-accent border-r-nyt-accent rounded-full transition-transform duration-1000 ease-out`}
                        style={{ transform: `rotate(${rotation}deg)` }}
                    />
                    {/* Needle */}
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
                    <span>{isMK ? 'ФОКУС' : 'FOKUS'}: {high_consensus_pct}%</span>
                    <span>{isMK ? 'ДИВЕРЗИТЕТ' : 'DIVERZITET'}: {pluralism_pct}%</span>
                </div>
            </div>
        </div>
    );
}
