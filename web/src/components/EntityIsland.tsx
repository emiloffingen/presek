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
    const API_URL = import.meta.env.PUBLIC_API_URL || (typeof window !== 'undefined' ? "/api" : "http://127.0.0.1:5000/api");
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
    <div className="entity-flow">
      <header className="entity-hero">
        <div className="entity-hero-main">
          <div className="entity-badge">
            {profile.type === 'PERSON' ? <User size={32} className="text-accent" /> : <Building2 size={32} className="text-accent" />}
          </div>
          <div className="entity-copy">
            <span className="entity-type">{profile.type}</span>
            <h1 className="entity-name">{profile.name}</h1>
          </div>
        </div>
        
        <div className="entity-metrics">
          <div className="entity-metric">
            <p>Споменувања</p>
            <strong>{profile.total_mentions}</strong>
          </div>
          <div className="entity-metric">
            <p>Прв пат виден</p>
            <strong>{new Date(profile.first_seen).toLocaleDateString('mk-MK')}</strong>
          </div>
          <div className="entity-metric">
            <p>Сентимент</p>
            <strong className="text-accent">{profile.sentiment_score > 0 ? '+' : ''}{profile.sentiment_score.toFixed(1)}</strong>
          </div>
        </div>
      </header>

      <div className="entity-grid">
        <div className="entity-summary">
          <h2 className="entity-section-title flex items-center gap-2"><TrendingUp size={14} /> Контекст</h2>
          <p className="entity-summary-copy">Профилот подолу ги собира присуствата, временската траекторија и поврзаните имиња што најчесто се појавуваат со {profile.name}.</p>
        </div>

        <aside className="entity-related">
          <div className="rail-card">
            <h3 className="rail-card-title flex items-center gap-2"><Link2 size={14} /> Поврзани Ентитети</h3>
            <div className="space-y-4">
              {related.map(rel => (
                <a 
                  key={rel.related_entity}
                  href={`/entity/${encodeURIComponent(rel.related_entity)}`}
                  className="entity-related-link"
                >
                  <span className="entity-related-name">{rel.related_entity}</span>
                  <div className="flex items-center gap-2">
                    <div className="entity-related-track">
                      <div className="h-full bg-accent" style={{ width: `${Math.min(rel.weight * 10, 100)}%` }} />
                    </div>
                    <span className="entity-related-weight">{rel.weight}</span>
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
