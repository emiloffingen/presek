import React, { useState, useEffect } from 'react';
import { TrendingUp, Users, Heart, Activity } from 'lucide-react';

interface Entity {
    name: string;
    total_mentions: number;
    sentiment_score: number;
    type: string;
}

interface Relationship {
    entity_a: string;
    entity_b: string;
    weight: number;
}

interface PulseOverview {
    trending: Entity[];
    sentiment: {
        positives: Entity[];
        negatives: Entity[];
    };
    relationships: Relationship[];
    updated_at: string;
}

const KnowledgeGraphIsland: React.FC<{ apiUrl: string }> = ({ apiUrl }) => {
    const [data, setData] = useState<PulseOverview | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${apiUrl}/intelligence/pulse-overview`)
            .then(res => res.json())
            .then(setData)
            .finally(() => setLoading(false));
    }, [apiUrl]);

    if (loading) return (
        <div className="animate-pulse space-y-8">
            <div className="h-64 bg-secondary/50 rounded-lg"></div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-[var(--grid-gap)]">
                <div className="h-48 bg-secondary/50 rounded-lg"></div>
                <div className="h-48 bg-secondary/50 rounded-lg"></div>
            </div>
        </div>
    );

    if (!data) return null;

    return (
        <div className="space-y-12">
            {/* Trending Entities */}
            <section>
                <div className="flex items-center gap-[var(--grid-gap)] mb-6 border-b border-border pb-4">
                    <TrendingUp size={20} className="text-nyt-accent" />
                    <h2 className="font-sans text-xs font-black uppercase tracking-widest">Aktuelni Subjekti</h2>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-[var(--grid-gap)]">
                    {data.trending.map((ent) => (
                        <a
                            key={ent.name}
                            href={`/subjekt/${encodeURIComponent(ent.name)}`}
                            className="p-4 border border-border bg-card hover:border-nyt-accent transition-all group"
                        >
                            <span className="text-[10px] font-black uppercase text-muted-foreground block mb-2">{ent.type || 'SUBJEKT'}</span>
                            <h3 className="font-serif font-bold text-lg leading-tight group-hover:text-nyt-accent">{ent.name}</h3>
                            <div className="mt-3 flex items-center justify-between">
                                <span className="text-[10px] font-bold uppercase">{ent.total_mentions} objavi</span>
                                <div className={`w-2 h-2 rounded-full ${ent.sentiment_score > 0.1 ? 'bg-green-500' : ent.sentiment_score < -0.1 ? 'bg-nyt-red' : 'bg-muted'}`}></div>
                            </div>
                        </a>
                    ))}
                </div>
            </section>

            {/* Sentiment Pulse */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-[var(--grid-gap)]">
                <section>
                    <div className="flex items-center gap-[var(--grid-gap)] mb-6 border-b border-border pb-4">
                        <Heart size={20} className="text-green-600" />
                        <h2 className="font-sans text-xs font-black uppercase tracking-widest">Pozitiven Puls</h2>
                    </div>
                    <div className="space-y-3">
                        {data.sentiment.positives.map((ent) => (
                            <div key={ent.name} className="flex items-center justify-between p-3 bg-green-500/5 border border-green-500/20 rounded">
                                <span className="font-serif font-bold">{ent.name}</span>
                                <span className="text-xs font-black text-green-600">+{ent.sentiment_score.toFixed(1)}</span>
                            </div>
                        ))}
                    </div>
                </section>

                <section>
                    <div className="flex items-center gap-[var(--grid-gap)] mb-6 border-b border-border pb-4">
                        <Activity size={20} className="text-nyt-red" />
                        <h2 className="font-sans text-xs font-black uppercase tracking-widest">Kriticen Puls</h2>
                    </div>
                    <div className="space-y-3">
                        {data.sentiment.negatives.map((ent) => (
                            <div key={ent.name} className="flex items-center justify-between p-3 bg-nyt-red/5 border border-nyt-red/20 rounded">
                                <span className="font-serif font-bold">{ent.name}</span>
                                <span className="text-xs font-black text-nyt-red">{ent.sentiment_score.toFixed(1)}</span>
                            </div>
                        ))}
                    </div>
                </section>
            </div>

            {/* Relationship Map */}
            <section>
                <div className="flex items-center gap-[var(--grid-gap)] mb-6 border-b border-border pb-4">
                    <Users size={20} className="text-nyt-accent" />
                    <h2 className="font-sans text-xs font-black uppercase tracking-widest">Mreza na Konekcii</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-[var(--grid-gap)]">
                    {data.relationships.map((rel, idx) => (
                        <div key={idx} className="flex items-center justify-center gap-[var(--grid-gap)] p-6 border border-border bg-secondary/10 rounded-lg italic font-serif">
                            <span className="font-bold">{rel.entity_a}</span>
                            <div className="flex-1 flex items-center gap-1 opacity-30">
                                <div className="h-px flex-1 bg-foreground"></div>
                                <span className="text-[10px] font-sans font-black not-italic">{rel.weight}</span>
                                <div className="h-px flex-1 bg-foreground"></div>
                            </div>
                            <span className="font-bold">{rel.entity_b}</span>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
};

export default KnowledgeGraphIsland;
