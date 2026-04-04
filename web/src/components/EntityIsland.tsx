import React, { useState, useEffect } from 'react';
import { User, Building2, TrendingUp, Link2, Loader2 } from 'lucide-react';

interface EntityProfile {
  name: string;
  type: string;
  total_mentions: number;
  first_seen: string;
  last_seen: string;
  sentiment_score: number;
}

interface Relationship {
  related_entity: string;
  weight: number;
}

export default function EntityIsland({ name }: { name: string }) {
  const [data, setData] = useState<{ profile: EntityProfile; related: Relationship[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const API_URL = import.meta.env.PUBLIC_API_URL || "http://localhost:5001/api";
    fetch(`${API_URL}/intelligence/entity/${encodeURIComponent(name)}`)
      .then(res => res.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name]);

  if (loading) return (
    <div className="flex flex-col items-center py-12">
      <Loader2 className="animate-spin text-accent" size={32} />
    </div>
  );

  if (!data) return null;

  const { profile, related } = data;

  return (
    <div className="space-y-10">
      <header className="border-b-4 border-double border-nyt pb-8">
        <div className="flex items-center gap-4 mb-4">
          <div className="p-3 bg-secondary rounded-full">
            {profile.type === 'PERSON' ? <User size={32} className="text-accent" /> : <Building2 size={32} className="text-accent" />}
          </div>
          <div>
            <span className="text-[10px] font-black uppercase tracking-widest text-muted">{profile.type}</span>
            <h1 className="text-4xl md:text-6xl font-serif font-bold text-primary">{profile.name}</h1>
          </div>
        </div>
        
        <div className="flex flex-wrap gap-8 mt-6">
          <div className="border-t border-nyt pt-3">
            <p className="text-[10px] font-black uppercase text-muted mb-1">Споменувања</p>
            <p className="text-2xl font-serif font-bold text-primary">{profile.total_mentions}</p>
          </div>
          <div className="border-t border-nyt pt-3">
            <p className="text-[10px] font-black uppercase text-muted mb-1">Прв пат виден</p>
            <p className="text-2xl font-serif font-bold text-primary">{new Date(profile.first_seen).toLocaleDateString('mk-MK')}</p>
          </div>
          <div className="border-t border-nyt pt-3">
            <p className="text-[10px] font-black uppercase text-muted mb-1">Сентимент</p>
            <p className="text-2xl font-serif font-bold text-accent">{profile.sentiment_score > 0 ? '+' : ''}{profile.sentiment_score.toFixed(1)}</p>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        <div className="lg:col-span-8">
          <h2 className="rail-label flex items-center gap-2"><TrendingUp size={14} /> НАЈНОВИ ВЕСТИ</h2>
          <p className="text-sm text-muted italic mb-8">Сите кластери каде се појавува {profile.name}...</p>
          {/* News feed will be handled by the parent Astro page */}
        </div>

        <aside className="lg:col-span-4">
          <div className="rail-widget border-t-2 border-primary pt-4">
            <h3 className="rail-label flex items-center gap-2"><Link2 size={14} /> ПОВРЗАНИ ЕНТИТЕТИ</h3>
            <div className="space-y-4">
              {related.map(rel => (
                <a 
                  key={rel.related_entity}
                  href={`/entity/${encodeURIComponent(rel.related_entity)}`}
                  className="flex justify-between items-center py-2 border-b border-nyt hover:text-accent transition-colors no-underline group"
                >
                  <span className="text-sm font-bold uppercase tracking-tight">{rel.related_entity}</span>
                  <div className="flex items-center gap-2">
                    <div className="h-1 w-12 bg-secondary overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${Math.min(rel.weight * 10, 100)}%` }} />
                    </div>
                    <span className="text-[10px] font-black text-muted">{rel.weight}</span>
                  </div>
                </a>
              ))}
              {related.length === 0 && <p className="text-xs text-muted italic">Нема пронајдени врски.</p>}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
