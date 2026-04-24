import React from 'react';
import type { Article } from '../types';

interface SourceSpectrumProps {
  articles: Article[];
}

const CATEGORY_MAP: Record<string, string> = {
  "MIA": "Агенциски", "MRT": "Јавен Сервис", "Sitel": "Главни", "Kanal 5": "Главни",
  "Telma": "Главни", "24 Вести": "Главни", "TV21": "Главни",
  "Sloboden Pecat": "Независни", "Fokus": "Независни", "Nezavisen": "Независни",
  "Meta": "Независни", "360 Stepeni": "Независни", "IRL": "Истражувачки",
  "Makfax": "Агенциски", "NetPress": "Алтернативни", "Kurir": "Алтернативни",
  "Republika": "Алтернативни", "Infomax": "Алтернативни",
  "Alsat-M": "Главни", "Pressing TV": "Главни", "Antropol": "Независни",
  "Bitola News": "Регионални",
  "PopUp": "Култура", "Kultura.mk": "Култура",
  "Reper": "Култура",
};

const CATEGORY_COLORS: Record<string, string> = {
  "Агенциски": "#3b82f6", // Blue
  "Јавен Сервис": "#10b981", // Green
  "Главни": "#f59e0b", // Amber
  "Независни": "#8b5cf6", // Purple
  "Истражувачки": "#ec4899", // Pink
  "Алтернативни": "#ef4444", // Red
  "Регионални": "#6366f1", // Indigo
  "Култура": "#14b8a6", // Teal
  "Локални": "#94a3b8", // Slate
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
    <div className="source-spectrum-container">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-secondary/30 mb-6">
        {stats.map((s) => (
          <div
            key={s.name}
            style={{ width: `${s.percentage}%`, backgroundColor: s.color }}
            className="h-full transition-all duration-500 hover:opacity-80"
            title={`${s.name}: ${s.count} извори`}
          />
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-y-4 gap-x-6">
        {stats.map((s) => (
          <div key={s.name} className="flex flex-col">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: s.color }}></span>
              <span className="text-[10px] font-black uppercase tracking-wider text-foreground">{s.name}</span>
              <span className="text-[10px] font-bold text-muted-foreground ml-auto">{Math.round(s.percentage)}%</span>
            </div>
            <p className="text-[10px] text-muted-foreground leading-tight truncate" title={s.sources.join(', ')}>
              {s.sources.join(', ')}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
