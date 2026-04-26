import React from 'react';
import type { Article } from '../types';

interface SourceSpectrumProps {
  articles: Article[];
}

const CATEGORY_MAP: Record<string, string> = {
  "MIA": "Агенциски", "Makfax": "Агенциски",
  "MRT": "Јавен Сервис", 
  "Sitel": "Главни", "Kanal 5": "Главни", "Telma": "Главни", "24 Вести": "Главни", "TV21": "Главни", "Alsat-M": "Главни", "Pressing TV": "Главни",
  "Sloboden Pecat": "Независни", "Fokus": "Независни", "Nezavisen": "Независни", "Meta": "Независни", "360 Stepeni": "Независни", "Antropol": "Независни", "RSE": "Независни", "DW": "Независни", "A1on": "Независни",
  "IRL": "Истражувачки", "Vistinomer": "Истражувачки", "Birn": "Истражувачки", "Prizma": "Истражувачки",
  "NetPress": "Алтернативни", "Kurir": "Алтернативни", "Republika": "Алтернативни", "Infomax": "Алтернативни", "Lider": "Алтернативни",
  "Plusinfo": "Локални", "Makpress": "Локални", "Libertas": "Локални", "Skopje1": "Локални", "Factor": "Локални", "Lokalno": "Локални", "Nova TV": "Локални", "Denesen": "Локални", "Ekonomski": "Локални",
  "Bitola News": "Регионални", "Ohrid1": "Регионални", "KumanovoNews": "Регионални",
  "PopUp": "Култура", "Kultura.mk": "Култура", "Reper": "Култура",
};

const CATEGORY_COLORS: Record<string, string> = {
  "Агенциски": "#3b82f6", 
  "Јавен Сервис": "#10b981", 
  "Главни": "#f59e0b", 
  "Независни": "#8b5cf6", 
  "Истражувачки": "#ec4899", 
  "Алтернативни": "#ef4444", 
  "Локални": "#0ea5e9", // Lighter blue for portal style
  "Регионални": "#6366f1", 
  "Култура": "#14b8a6", 
};

export const SourceSpectrum: React.FC<SourceSpectrumProps> = ({ articles }) => {
  const stats = React.useMemo(() => {
    const counts: Record<string, number> = {};
    const sourcesByCategory: Record<string, string[]> = {};
    
    articles.forEach(art => {
      const cat = CATEGORY_MAP[art.source] || "Локални";
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
        color: CATEGORY_COLORS[name] || CATEGORY_COLORS["Локални"],
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
            title={`${s.name}: ${s.count} извори`}
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
