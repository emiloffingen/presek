import React, { useEffect, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Activity, Smile, Meh, Frown, Info } from 'lucide-react';

interface MoodData {
    mood: string;
    score: number;
    objectivity: number;
    sample_size: number;
}

interface TrendDay {
    day: string;
    score: number;
    label: string;
    objectivity: number;
    count: number;
}

export default function NationalMoodIsland({ lang = 'sr' }: { lang?: string }) {
    const [mood, setMood] = useState<MoodData | null>(null);
    const [trends, setTrends] = useState<TrendDay[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                const base = apiBaseUrl();
                const [moodRes, trendsRes] = await Promise.all([
                    fetch(`${base}/stats/mood?lang=${lang}`),
                    fetch(`${base}/stats/sentiment-trends?lang=${lang}`)
                ]);

                let moodJson = null;
                let trendsJson = null;

                if (moodRes.ok) {
                    try {
                        moodJson = await moodRes.json();
                    } catch (e) {
                        console.warn('Failed to parse mood JSON:', e);
                    }
                } else {
                    console.warn(`Failed to fetch mood: status ${moodRes.status}`);
                }

                if (trendsRes.ok) {
                    try {
                        trendsJson = await trendsRes.json();
                    } catch (e) {
                        console.warn('Failed to parse trends JSON:', e);
                    }
                } else {
                    console.warn(`Failed to fetch trends: status ${trendsRes.status}`);
                }

                if (moodJson && moodJson.status === 'success') setMood(moodJson);
                if (trendsJson && trendsJson.status === 'success') setTrends(trendsJson.data);
            } catch (err) {
                console.error('Failed to fetch mood data', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [lang]);

    if (loading) {
        return (
            <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6 shadow-sm opacity-60 animate-pulse">
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded-full bg-zinc-200 dark:bg-zinc-800"></div>
                        <div className="h-3 w-32 bg-zinc-200 dark:bg-zinc-800 rounded"></div>
                    </div>
                </div>
                <div className="space-y-8">
                    <div className="h-1.5 w-full bg-zinc-100 dark:bg-zinc-900 rounded-full"></div>
                    <div className="grid grid-cols-2 gap-6 pt-4 border-t border-zinc-100 dark:border-zinc-800">
                        <div className="space-y-2">
                            <div className="h-2 w-16 bg-zinc-100 dark:bg-zinc-800 rounded"></div>
                            <div className="h-6 w-12 bg-zinc-100 dark:bg-zinc-800 rounded"></div>
                        </div>
                        <div className="flex flex-col items-end space-y-2">
                            <div className="h-2 w-20 bg-zinc-100 dark:bg-zinc-800 rounded"></div>
                            <div className="flex gap-1.5 h-10 items-end">
                                {[1,2,3,4,5].map(i => (
                                    <div key={i} className="w-2 bg-zinc-100 dark:bg-zinc-800 rounded-t-sm" style={{ height: `${20 + i*15}%` }}></div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }
    if (!mood) {
        return (
            <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6 shadow-sm opacity-80">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <Activity size={18} className="text-muted-foreground/40" />
                        <h3 className="font-black text-xs uppercase tracking-widest text-muted-foreground/40">{lang === 'sr' ? 'Nacionalni Puls' : 'Национален Пулс'}</h3>
                    </div>
                </div>
                <div className="py-10 flex flex-col items-center justify-center text-center">
                    <div className="w-12 h-12 rounded-full bg-zinc-50 dark:bg-zinc-900 flex items-center justify-center mb-4">
                        <Meh size={28} className="text-muted-foreground/20" />
                    </div>
                    <p className="text-sm font-serif italic text-muted-foreground/60 px-4">
                        {lang === 'sr' ? 'Sistemska kalibracija u toku...' : 'Системска калибрација во тек...'}
                    </p>
                    <p className="text-[9px] uppercase font-black tracking-[0.2em] text-muted-foreground/30 mt-4">
                        {lang === 'sr' ? 'Nedostaje dovoljno podataka' : 'Недостасуваат доволно податоци'}
                    </p>
                </div>
            </div>
        );
    }

    const getMoodIcon = (score: number) => {
        if (score > 0.2) return <Smile className="text-emerald-500" size={20} />;
        if (score < -0.2) return <Frown className="text-red-500" size={20} />;
        return <Meh className="text-amber-500" size={20} />;
    };

    // Calculate indicator position (-1 to 1 map to 0% to 100%)
    const indicatorPos = ((mood.score + 1) / 2) * 100;

    return (
        <div className="relative overflow-hidden rounded-xl p-6 shadow-premium transition-all duration-500 national-mood-card group">
            <style>{`
                .national-mood-card {
                  background: linear-gradient(135deg, rgba(254, 252, 246, 0.75) 0%, rgba(246, 240, 228, 0.7) 100%);
                  backdrop-filter: var(--glass-blur);
                  -webkit-backdrop-filter: var(--glass-blur);
                  border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
                  box-shadow: 0 8px 32px 0 color-mix(in srgb, var(--background) 30%, rgba(0, 0, 0, 0.08)),
                              inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 6%, transparent);
                  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                }
                
                .dark .national-mood-card {
                  background: linear-gradient(135deg, rgba(22, 26, 41, 0.7) 0%, rgba(15, 18, 29, 0.65) 100%);
                  border-color: color-mix(in srgb, var(--border) 80%, transparent);
                  box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.3),
                              inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 4%, transparent);
                }
                
                .national-mood-card:hover {
                  border-color: color-mix(in srgb, var(--nyt-accent) 35%, var(--border));
                  box-shadow: 0 16px 48px 0 color-mix(in srgb, var(--background) 50%, rgba(0, 0, 0, 0.18)),
                              inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 10%, transparent),
                              0 0 30px -4px color-mix(in srgb, var(--nyt-accent) 6%, transparent);
                  transform: translateY(-2px);
                }
                
                .mood-trend-column {
                  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                }
                
                .mood-trend-column:hover {
                  transform: scaleY(1.15) scaleX(1.3);
                  filter: brightness(1.25);
                }
            `}</style>
            
            {/* Ambient Background Gradient */}
            <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.08] pointer-events-none bg-gradient-to-br from-nyt-accent via-transparent to-emerald-500 group-hover:opacity-10 transition-opacity duration-700" />
            
            <div className="relative z-10 flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="organic-pulse-wrap text-nyt-accent">
                        <Activity size={18} className="relative z-10" />
                        <div className="organic-pulse-ring" />
                        <div className="organic-pulse-ring" />
                    </div>
                    <h3 className="font-black text-xs uppercase tracking-[0.2em] premium-kicker">{lang === 'sr' ? 'Nacionalni Puls' : 'Национален Пулс'}</h3>
                </div>
                <div className="group relative">
                    <Info size={14} className="text-muted-foreground/60 cursor-help hover:text-nyt-accent transition-colors" />
                    <div className="absolute right-0 bottom-full mb-3 w-56 p-3 bg-black/90 backdrop-blur-md text-white text-[11px] rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-all transform translate-y-1 group-hover:translate-y-0 z-50 leading-relaxed">
                        {lang === 'sr'
                          ? 'Sistemska analiza emotivnog tona i objektivnosti u medijskom prostoru za poslednjih 24 časa.'
                          : 'Системска анализа на емотивниот тон и објективноста во медиумскиот простор за последните 24 часа.'}
                    </div>
                </div>
            </div>

            <div className="relative z-10 space-y-8">
                {/* Mood Meter */}
                <div>
                    <div className="flex justify-between text-[10px] font-black uppercase tracking-widest mb-3 opacity-60">
                        <span className="text-red-600">{lang === 'sr' ? 'Negativan' : 'Негативен'}</span>
                        <span>{lang === 'sr' ? 'Neutralan' : 'Неутрален'}</span>
                        <span className="text-emerald-600">{lang === 'sr' ? 'Pozitivan' : 'Позитивен'}</span>
                    </div>
                    <div className="relative h-1.5 w-full bg-zinc-100 dark:bg-zinc-900 rounded-full overflow-visible">
                        <div
                            className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 bg-white dark:bg-zinc-950 border-[3px] rounded-full shadow-lg transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) z-20"
                            style={{
                                left: `${indicatorPos}%`,
                                marginLeft: '-7px',
                                borderColor: mood.score > 0.2 ? '#10b981' : mood.score < -0.2 ? '#ef4444' : '#f59e0b',
                                boxShadow: mood.score > 0.2 ? '0 0 10px 2px rgba(16,185,129,0.5)' : mood.score < -0.2 ? '0 0 10px 2px rgba(239,68,68,0.5)' : '0 0 10px 2px rgba(245,158,11,0.5)'
                            }}
                        />
                        <div className="absolute inset-0 bg-gradient-to-r from-red-500/20 via-zinc-200/10 dark:via-zinc-800/10 to-emerald-500/20 rounded-full" />
                    </div>
                    <div className="mt-4 flex items-center justify-between">
                        <div className="flex items-center gap-3 transition-transform duration-500 group-hover:translate-x-1">
                            {getMoodIcon(mood.score)}
                            <span className="text-base font-serif italic font-black capitalize tracking-tight">{mood.mood}</span>
                        </div>
                        <span className="text-[10px] font-mono font-bold text-muted-foreground/70 tracking-tighter">
                            N={mood.sample_size.toLocaleString()} {lang === 'sr' ? 'događaja' : 'настани'}
                        </span>
                    </div>
                </div>

                {/* Sub-metrics */}
                <div className="grid grid-cols-2 gap-6 pt-4 border-t border-zinc-100 dark:border-zinc-800/50">
                    <div className="magnetic-item">
                        <p className="text-[9px] uppercase font-black tracking-widest text-muted-foreground/60 mb-2">{lang === 'sr' ? 'Objektivnost' : 'Објективност'}</p>
                        <div className="flex items-baseline gap-1">
                            <span className="text-2xl font-black tabular-nums tracking-tighter">{(mood.objectivity * 100).toFixed(0)}</span>
                            <span className="text-xs font-bold opacity-40">%</span>
                        </div>
                    </div>
                    <div className="flex flex-col items-end magnetic-item">
                        <p className="text-[9px] uppercase font-black tracking-widest text-muted-foreground/60 mb-2 text-right">{lang === 'sr' ? 'Trendovi (7d)' : 'Трендови (7д)'}</p>
                        <div className="flex gap-1.5 h-12 items-end">
                            {trends.map((t, i) => (
                                <div
                                    key={i}
                                    className="w-2 rounded-t-[2px] mood-trend-column"
                                    style={{
                                        height: `${Math.max(15, (t.objectivity * 100))}%`,
                                        backgroundColor: t.score > 0.1 ? '#10b981' : t.score < -0.1 ? '#ef4444' : '#71717a',
                                        opacity: 0.3 + (i * 0.1)
                                    } as any}
                                    title={`${t.day}: ${t.label} (Obj: ${t.objectivity})`}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
