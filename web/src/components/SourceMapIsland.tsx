import React, { useEffect, useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Zap } from 'lucide-react';

interface SourceActivity {
  source: string;
  activity_score: number;
}

export default function SourceMapIsland({ lang = 'sr' }: { lang?: string }) {
  const [sources, setSources] = useState<SourceActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const isMK = lang === 'mk';

  useEffect(() => {
    const API_URL = apiBaseUrl();
    fetch(`${API_URL}/intelligence/live-map?lang=${lang}`)
      .then(res => res.json())
      .then(json => {
        if (json.status === 'success') {
          setSources(json.data || []);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [lang]);

  if (loading || sources.length === 0) return null;

  // Take top 40 for the wall
  const displaySources = sources.slice(0, 40);
  const maxScore = Math.max(...displaySources.map(s => s.activity_score), 1);

  return (
    <section className="rail-module motion-rise-fast">
      <h3 className="rail-title flex items-center gap-[var(--grid-gap)]">
        <Zap size={14} className="text-nyt-accent fill-nyt-accent" /> {isMK ? 'ПОКРИЕНОСТ ВО ЖИВО' : 'POKRIVENOST UŽIVO'}
      </h3>
      <p className="rail-note mb-4">
        {isMK ? '60+ извори се скенираат на секои 5 минути.' : '60+ izvora se skenira na svakih 5 minuta.'}
      </p>

      <div className="flex flex-wrap gap-1.5 opacity-80">
        {displaySources.map((s, idx) => {
          const intensity = Math.min(0.2 + (s.activity_score / maxScore) * 0.8, 1);
          const isHot = s.activity_score > maxScore * 0.7;

          return (
            <div
              key={s.source}
              className={`text-[9px] font-black uppercase tracking-tighter px-1.5 py-0.5 rounded-sm border border-border/50 transition-all duration-1000`}
              style={{
                backgroundColor: `rgba(165, 197, 255, ${intensity * 0.15})`,
                color: isHot ? 'var(--nyt-accent)' : 'var(--muted-foreground)',
                borderColor: isHot ? 'rgba(165, 197, 255, 0.3)' : 'transparent'
              }}
            >
              <span className={isHot ? 'animate-pulse' : ''}>{s.source}</span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 border-t border-border flex justify-between items-center">
        <span className="text-[10px] font-bold text-muted-foreground uppercase">{isMK ? 'Системски статус' : 'Sistemski status'}</span>
        <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-[10px] font-black text-green-500 uppercase">{isMK ? 'Активен' : 'Aktivan'}</span>
        </div>
      </div>
    </section>
  );
}
