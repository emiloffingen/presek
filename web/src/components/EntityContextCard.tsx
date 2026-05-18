import React, { useEffect, useState } from 'react';
import { User, TrendingUp, Loader2 } from 'lucide-react';

interface EntityContextCardProps {
  name: string;
}

export default function EntityContextCard({ name }: EntityContextCardProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/entity-graph/${encodeURIComponent(name)}`)
      .then(res => res.json())
      .then(json => {
        if (json.status === 'success') setData(json.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name]);

  if (loading) return <div className="p-4 bg-background border border-border flex items-center gap-[var(--grid-gap)]"><Loader2 className="animate-spin text-nyt-accent" size={14} /> <span className="text-[10px] uppercase font-black">Vcituvam kontekst...</span></div>;
  if (!data) return null;

  return (
    <div className="group relative">
        <div className="flex items-center gap-[var(--grid-gap)] px-3 py-1.5 bg-secondary/30 border border-border rounded-sm hover:border-nyt-accent transition-colors cursor-help">
            <User size={12} className="text-nyt-accent" />
            <span className="text-[11px] font-bold uppercase tracking-tight">{name}</span>
            <div className="ml-2 w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" title="Aktiven subjekt"></div>
        </div>

        {/* Hover Popover */}
        <div className="absolute bottom-full left-0 mb-3 w-64 bg-background border-2 border-foreground shadow-2xl opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all z-50 pointer-events-none group-hover:pointer-events-auto">
            <div className="p-4">
                <div className="flex justify-between items-start mb-3 pb-2 border-b border-border">
                    <span className="text-[9px] font-black uppercase tracking-[0.2em] text-nyt-accent">kontekst Karta</span>
                    <div className="flex items-center gap-1.5 bg-secondary px-2 py-0.5 rounded-full">
                        <TrendingUp size={10} />
                        <span className="text-[9px] font-black">{data.importance_score}</span>
                    </div>
                </div>

                <h4 className="font-serif font-black text-lg mb-2">{name}</h4>
                <p className="text-xs font-nyt-body leading-relaxed text-secondary-foreground mb-4">
                    {data.bio_summary || `Ovaj subjekt se redovno prati u okviru srpskog medijskog prostora preko sistema Presek.`}
                </p>

                <div className="flex items-center justify-between pt-3 border-t border-border">
                    <span className="text-[8px] font-black uppercase text-muted-foreground tracking-widest">Posledno viđeno: {new Date(data.last_seen).toLocaleDateString('sr-RS')}</span>
                    <a href={`/subjekt/${encodeURIComponent(name)}`} className="text-[9px] font-black uppercase text-nyt-accent border-b border-nyt-accent">Profil</a>
                </div>
            </div>
            {/* Pointer notch */}
            <div className="absolute top-full left-6 w-3 h-3 bg-background border-r-2 border-b-2 border-foreground rotate-45 -translate-y-1.5"></div>
        </div>
    </div>
  );
}
