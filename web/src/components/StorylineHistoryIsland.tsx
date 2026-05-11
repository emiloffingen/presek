import React, { useState, useEffect } from 'react';
import { History, ArrowRight, Calendar } from 'lucide-react';

interface StorylineItem {
    cluster_id: string;
    title: string;
    first_seen: string;
    similarity: number;
    image_url?: string;
}

const StorylineHistoryIsland: React.FC<{ clusterId: string; apiUrl: string }> = ({ clusterId, apiUrl }) => {
    const [history, setHistory] = useState<StorylineItem[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${apiUrl}/intelligence/cluster/${clusterId}/history`)
            .then(res => res.json())
            .then(data => {
                setHistory(data.history || []);
            })
            .finally(() => setLoading(false));
    }, [clusterId, apiUrl]);

    if (loading) return null;
    if (history.length === 0) return null;

    return (
        <section className="mt-16 pt-12 border-t border-border">
            <div className="flex items-center gap-3 mb-10">
                <History size={20} className="text-nyt-accent" />
                <h2 className="font-sans text-xs font-black uppercase tracking-widest">Hronologija na razvojot</h2>
            </div>

            <div className="relative pl-8 space-y-10 before:content-[''] before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-px before:bg-border">
                {history.map((item) => (
                    <div key={item.cluster_id} className="relative">
                        {/* Dot */}
                        <div className="absolute -left-[30px] top-1.5 w-4 h-4 rounded-full border-2 border-nyt-accent bg-background z-10"></div>
                        
                        <div className="flex flex-col md:flex-row md:items-start gap-5">
                            <div className="md:w-32 flex-shrink-0 pt-1">
                                <span className="font-sans text-[10px] font-black uppercase text-muted-foreground flex items-center gap-1">
                                    <Calendar size={10} />
                                    {new Date(item.first_seen).toLocaleDateString('mk-RS', { day: 'numeric', month: 'short' })}
                                </span>
                            </div>
                            
                            <a href={`/cluster/${item.cluster_id}`} className="group flex-1 flex gap-4 items-start">
                                <div className="flex-1">
                                    <h3 className="font-serif font-bold text-base md:text-lg leading-tight group-hover:text-nyt-accent transition-colors">
                                        {item.title}
                                    </h3>
                                    <div className="mt-2 flex items-center gap-2 text-[10px] font-black uppercase text-nyt-accent opacity-0 group-hover:opacity-100 transition-opacity">
                                        Vidi im detalite <ArrowRight size={12} />
                                    </div>
                                </div>
                                {item.image_url && (
                                    <div className="w-16 h-16 md:w-20 md:h-20 flex-shrink-0">
                                        <img 
                                            src={`/proxy?url=${encodeURIComponent(item.image_url)}&w=160`} 
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
