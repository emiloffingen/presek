import React from 'react';
import type { Article } from '../types';

interface SourceSpectrumProps {
  articles: Article[];
}

const CATEGORY_MAP: Record<string, string> = {
  "MIA": "Agenciski", "Makfax": "Agenciski",
  "MRT": "Javen Servis", 
  "Sitel": "glavni", "Kanal 5": "glavni", "Telma": "glavni", "24 vesti": "glavni", "TV21": "glavni", "Alsat-M": "glavni", "Pressing TV": "glavni",
  "Sloboden Pecat": "Nezavisni", "Fokus": "Nezavisni", "Nezavisen": "Nezavisni", "Meta": "Nezavisni", "360 Stepeni": "Nezavisni", "Antropol": "Nezavisni", "RSE": "Nezavisni", "DW": "Nezavisni", "A1on": "Nezavisni",
  "IRL": "Istrazuvacki", "Vistinomer": "Istrazuvacki", "Birn": "Istrazuvacki", "Prizma": "Istrazuvacki",
  "NetPress": "Alternativni", "Kurir": "Alternativni", "Republika": "Alternativni", "Infomax": "Alternativni", "Lider": "Alternativni",
  "Plusinfo": "Lokalni", "Makpress": "Lokalni", "Libertas": "Lokalni", "Skopje1": "Lokalni", "Factor": "Lokalni", "Lokalno": "Lokalni", "Nova TV": "Lokalni", "Denesen": "Lokalni", "Ekonomski": "Lokalni",
  "Bitola News": "Regionalni", "Ohrid1": "Regionalni", "KumanovoNews": "Regionalni",
  "PopUp": "Kultura", "Kultura.mk": "Kultura", "Reper": "Kultura",
};

const CATEGORY_COLORS: Record<string, string> = {
  "Agenciski": "#3b82f6", 
  "Javen Servis": "#10b981", 
  "glavni": "#f59e0b", 
  "Nezavisni": "#8b5cf6", 
  "Istrazuvacki": "#ec4899", 
  "Alternativni": "#ef4444", 
  "Lokalni": "#0ea5e9", // Lighter blue for portal style
  "Regionalni": "#6366f1", 
  "Kultura": "#14b8a6", 
};

export const SourceSpectrum: React.FC<SourceSpectrumProps> = ({ articles }) => {
  const stats = React.useMemo(() => {
    const counts: Record<string, number> = {};
    const sourcesByCategory: Record<string, string[]> = {};
    
    articles.forEach(art => {
      const cat = CATEGORY_MAP[art.source] || "Lokalni";
      counts[cat] = (counts[cat] || 0) + 1;
      if (!sourcesByCategory[cat]) sourcesByCategory[cat] = [];
      if (!sourcesByCategory[cat].includes(art.source)) {
        sourcesByCategory[cat].push(art.source);
      }
    });
    
    const total = articles.length;
    return Object.entries(counts)
      .map(([name, count]) => ({
        name,
        count,
        percentage: (count / total) * 100,
        color: CATEGORY_COLORS[name] || CATEGORY_COLORS["Lokalni"],
        sources: sourcesByCategory[name]
      }))
      .sort((a, b) => b.count - a.count);
  }, [articles]);

  return (
    <div className="source-spectrum-container p-2 bg-secondary/5 rounded-lg border border-border/40">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-secondary/30 mb-6 shadow-inner">
        {stats.map((s) => (
          <div
            key={s.name}
            style={{ width: `${s.percentage}%`, backgroundColor: s.color }}
            className="h-full transition-all duration-700 hover:opacity-80 border-r border-background/20 last:border-0"
            title={`${s.name}: ${s.count} izvori`}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-5 gap-x-8">
        {stats.map((s) => (
          <div key={s.name} className="flex flex-col group">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-[2px] transition-transform group-hover:scale-110" style={{ backgroundColor: s.color }}></div>
                <span className="text-[11px] font-black uppercase tracking-tighter text-foreground/90">{s.name}</span>
              </div>
              <span className="text-[11px] font-black tabular-nums text-foreground/70">{Math.round(s.percentage)}%</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {s.sources.map((src, idx) => (
                <span key={src} className="text-[10px] font-bold text-muted-foreground whitespace-nowrap">
                  {src}{idx < s.sources.length - 1 && <span className="ml-1 opacity-30 text-foreground">,</span>}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
