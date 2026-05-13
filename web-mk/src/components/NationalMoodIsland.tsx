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

export default function NationalMoodIsland() {
    const [mood, setMood] = useState<MoodData | null>(null);
    const [trends, setTrends] = useState<TrendDay[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                const base = apiBaseUrl();
                const [moodRes, trendsRes] = await Promise.all([
                    fetch(`${base}/stats/mood`),
                    fetch(`${base}/stats/sentiment-trends`)
                ]);
                
                const moodJson = await moodRes.json();
                const trendsJson = await trendsRes.json();

                if (moodJson.status === 'success') setMood(moodJson);
                if (trendsJson.status === 'success') setTrends(trendsJson.data);
            } catch (err) {
                console.error('Failed to fetch mood data', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, []);

    if (loading) return <div className="h-32 animate-pulse bg-muted rounded-xl" />;
    if (!mood) return null;

    const getMoodIcon = (score: number) => {
        if (score > 0.2) return <Smile className="text-emerald-500" size={20} />;
        if (score < -0.2) return <Frown className="text-red-500" size={20} />;
        return <Meh className="text-amber-500" size={20} />;
    };

    // Calculate indicator position (-1 to 1 map to 0% to 100%)
    const indicatorPos = ((mood.score + 1) / 2) * 100;

    return (
        <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Activity size={18} className="text-nyt-accent" />
                    <h3 className="font-bold text-sm uppercase tracking-tighter">Nacionalen Puls</h3>
                </div>
                <div className="group relative">
                    <Info size={14} className="text-muted-foreground cursor-help" />
                    <div className="absolute right-0 bottom-full mb-2 w-48 p-2 bg-black text-white text-[10px] rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                        Sistemska analiza na emotivniot ton i objektivnosta vo mediumskiot prostor za poslednite 24 casa.
                    </div>
                </div>
            </div>

            <div className="space-y-6">
                {/* Mood Meter */}
                <div>
                    <div className="flex justify-between text-[11px] font-bold uppercase mb-2">
                        <span className="text-red-600">Negativen</span>
                        <span className="text-muted-foreground">Neutralen</span>
                        <span className="text-emerald-600">Pozitiven</span>
                    </div>
                    <div className="relative h-2 w-full bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                        <div 
                            className="absolute top-0 bottom-0 w-1 bg-black dark:bg-white transition-all duration-1000 ease-out z-10"
                            style={{ left: `${indicatorPos}%`, marginLeft: '-2px' }}
                        />
                        <div className="absolute inset-0 bg-gradient-to-r from-red-500/20 via-transparent to-emerald-500/20" />
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            {getMoodIcon(mood.score)}
                            <span className="text-sm font-serif italic capitalize">{mood.mood}</span>
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground">
                            N={mood.sample_size} nastani
                        </span>
                    </div>
                </div>

                {/* Sub-metrics */}
                <div className="grid grid-cols-2 gap-4 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                    <div>
                        <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Objektivnost</p>
                        <div className="flex items-end gap-1">
                            <span className="text-xl font-black tabular-nums">{(mood.objectivity * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                    <div className="flex flex-col items-end">
                        <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1 text-right">Trendovi (7d)</p>
                        <div className="flex gap-1.5 h-12 items-end">
                            {trends.map((t, i) => (
                                <div 
                                    key={i}
                                    className="w-2.5 rounded-t-sm transition-all hover:opacity-80"
                                    style={{ 
                                        height: `${Math.max(20, (t.objectivity * 100))}%`,
                                        backgroundColor: t.score > 0.1 ? '#10b981' : t.score < -0.1 ? '#ef4444' : '#71717a'
                                    }}
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
