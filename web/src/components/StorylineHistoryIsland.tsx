import React, { useState, useEffect } from 'react';
import { History, ArrowRight, Calendar } from 'lucide-react';
import { localePathForLang } from '../lib/localePaths';
import { proxyUrl } from '../lib/apiBase';

interface StorylineItem {
    cluster_id: string;
    title: string;
    first_seen: string;
    similarity: number;
    image_url?: string;
}

const StorylineHistoryIsland: React.FC<{ clusterId: string; apiUrl: string; lang?: string }> = ({ clusterId, apiUrl, lang = 'sr' }) => {
    const [history, setHistory] = useState<StorylineItem[]>([]);
    const [loading, setLoading] = useState(true);
    const isMK = lang === 'mk';

    useEffect(() => {
        fetch(`${apiUrl}/intelligence/cluster/${clusterId}/history?lang=${lang}`)
            .then(res => res.json())
            .then(data => {
                setHistory(data.history || []);
            })
            .finally(() => setLoading(false));
    }, [clusterId, apiUrl, lang]);

    if (loading) return null;
    if (history.length === 0) return null;

    return (
        <section className="mt-16 pt-12 border-t border-border">
            <div className="flex items-center gap-[var(--grid-gap)] mb-10">
                <History size={20} className="text-nyt-accent" />
                <h2 className="ui-kicker">
                    {isMK ? 'Хронологија на развојот' : 'Hronologija razvoja'}
                </h2>
            </div>

            <div className="relative pl-8 space-y-10 before:content-[''] before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-px before:bg-border">
                {history.map((item) => (
                    <div key={item.cluster_id} className="relative">
                        {/* Dot */}
                        <div className="absolute -left-[30px] top-1.5 w-4 h-4 rounded-full border-2 border-nyt-accent bg-background z-10"></div>

                        <div className="flex flex-col md:flex-row md:items-start gap-5">
                            <div className="md:w-32 flex-shrink-0 pt-1">
                                <span className="ui-kicker flex items-center gap-1">
                                    <Calendar size={10} />
                                    {new Date(item.first_seen).toLocaleDateString(isMK ? 'mk-MK' : 'sr-RS', { day: 'numeric', month: 'short' })}
                                </span>
                            </div>

                            <a href={localePathForLang(`/cluster/${item.cluster_id}`, isMK ? 'mk' : 'sr')} className="group flex-1 flex gap-[var(--grid-gap)] items-start">
                                <div className="flex-1">
                                    <h3 className="font-serif font-bold text-base md:text-lg leading-tight group-hover:text-nyt-accent transition-colors">
                                        {item.title}
                                    </h3>
                                    <div className="mt-2 flex items-center gap-[var(--grid-gap)] ui-kicker ui-kicker--accent opacity-0 group-hover:opacity-100 transition-opacity">
                                        {isMK ? 'Види ги деталите' : 'Vidi detalje'} <ArrowRight size={12} />
                                    </div>
                                </div>
                                {item.image_url && (
                                    <div className="w-16 h-16 md:w-20 md:h-20 flex-shrink-0">
                                        <img
                                            src={proxyUrl(`/proxy?url=${encodeURIComponent(item.image_url)}&w=160`)}
                                            alt={item.title}
                                            className="w-full h-full object-cover rounded border border-border group-hover:border-nyt-accent transition-colors"
                                        />
                                    </div>
                                )}
                            </a>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
};

export default StorylineHistoryIsland;
