import React from 'react';
import { Target, Activity } from 'lucide-react';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { pulse } from '../../i18n/namespaces/pulse';

interface TopicSentiment {
    topic: string;
    avg_sentiment: number;
    avg_objectivity: number;
    avg_sensationalism: number;
    n: number;
}

interface RadarProps {
    data: TopicSentiment[];
    lang?: string;
}

export default function SentimentRadarIsland({ data, lang = 'mk' }: RadarProps) {
    const locale = lang === 'mk' ? 'mk' : 'sr';
    const t = useClientTranslations(locale, pulse);
    const displayData = data.slice(0, 8);
    if (displayData.length === 0) return null;

    return (
        <div className="bg-card border border-border p-6 rounded-xl shadow-sm h-full flex flex-col">
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <Target size={18} className="text-nyt-red" />
                    <h3 className="font-bold text-sm uppercase tracking-tighter">
                        {t('pulse.radar_title')}
                    </h3>
                </div>
                <div className="flex items-center gap-1.5 text-[9px] font-black uppercase text-muted-foreground opacity-50">
                    <Activity size={10} />
                    {t('pulse.radar_by_topic')}
                </div>
            </div>

            <div className="flex-1 space-y-6">
                {displayData.map((item) => {
                    const sentiment = item.avg_sentiment;
                    const posWidth = Math.max(0, sentiment) * 100;
                    const negWidth = Math.max(0, -sentiment) * 100;

                    return (
                        <div key={item.topic} className="group">
                            <div className="flex justify-between items-end mb-1.5">
                                <div className="flex flex-col">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-foreground group-hover:text-presek-mark transition-colors">
                                        {item.topic}
                                    </span>
                                    <span className="text-[8px] text-muted-foreground font-serif italic">
                                        {item.n} {t('pulse.radar_stories_analyzed')}
                                    </span>
                                </div>
                                <span className={`text-[10px] font-black tabular-nums ${sentiment > 0.1 ? 'text-emerald-500' : sentiment < -0.1 ? 'text-nyt-red' : 'text-muted-foreground'}`}>
                                    {sentiment > 0 ? '+' : ''}{sentiment.toFixed(2)}
                                </span>
                            </div>

                            <div className="relative h-2 w-full bg-secondary/30 rounded-full overflow-hidden flex">
                                <div className="flex-1 flex justify-end pr-px">
                                    <div
                                        className="h-full bg-nyt-red/60 transition-all duration-1000 origin-right"
                                        style={{ width: `${negWidth}%` }}
                                    />
                                </div>
                                <div className="w-px h-full bg-foreground/20 z-10" />
                                <div className="flex-1 flex justify-start pl-px">
                                    <div
                                        className="h-full bg-emerald-500/60 transition-all duration-1000 origin-left"
                                        style={{ width: `${posWidth}%` }}
                                    />
                                </div>
                            </div>

                            <div className="flex justify-between mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span className="text-[7px] font-bold text-muted-foreground uppercase">
                                    {t('pulse.radar_objectivity_short')}: {(item.avg_objectivity * 100).toFixed(0)}%
                                </span>
                                <span className="text-[7px] font-bold text-muted-foreground uppercase">
                                    {t('pulse.radar_sensationalism_short')}: {(item.avg_sensationalism * 100).toFixed(0)}%
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="mt-6 pt-6 border-t border-border/50 grid grid-cols-2 gap-[var(--grid-gap)]">
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span className="text-[8px] font-black uppercase text-muted-foreground">{t('pulse.sentiment_positive')}</span>
                </div>
                <div className="flex items-center gap-[var(--grid-gap)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-nyt-red" />
                    <span className="text-[8px] font-black uppercase text-muted-foreground">{t('pulse.sentiment_critical')}</span>
                </div>
            </div>
        </div>
    );
}
