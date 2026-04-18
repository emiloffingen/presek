import React, { useEffect, useState } from 'react';
import { Loader2, CalendarRange } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

interface HeatmapDay {
  day: string;
  total_clusters: number;
  breaking_clusters: number;
}

export default function ArchiveHeatmapIsland() {
  const [data, setData] = useState<HeatmapDay[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${apiBaseUrl()}/archive/heatmap`)
      .then(res => res.json())
      .then(json => {
        if (json.status === 'success') {
          setData(json.data);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-24">
        <Loader2 className="animate-spin text-nyt-accent" />
      </div>
    );
  }

  if (data.length === 0) return null;

  // Find max values for color scaling
  const maxTotal = Math.max(...data.map(d => d.total_clusters), 1);
  const maxBreaking = Math.max(...data.map(d => d.breaking_clusters), 1);

  // Fill in missing days to make a complete 90-day grid
  const today = new Date();
  const grid = [];
  for (let i = 89; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const existing = data.find(x => x.day === dateStr);
    grid.push(existing || { day: dateStr, total_clusters: 0, breaking_clusters: 0 });
  }

  const getIntensityClass = (count: number, max: number, isBreaking: boolean) => {
    if (count === 0) return 'bg-muted/30 border border-border/20';
    const ratio = count / max;
    if (isBreaking) {
      if (ratio > 0.7) return 'bg-nyt-red text-white font-bold shadow-[0_0_10px_rgba(185,28,28,0.4)]';
      if (ratio > 0.3) return 'bg-nyt-red/80 text-white font-bold';
      return 'bg-nyt-red/50';
    } else {
      if (ratio > 0.7) return 'bg-nyt-accent text-white font-bold shadow-[0_0_10px_rgba(30,64,175,0.4)]';
      if (ratio > 0.3) return 'bg-nyt-accent/80 text-white';
      return 'bg-nyt-accent/50';
    }
  };

  const getLabel = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('mk-MK', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-6 mb-8 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="font-serif text-xl font-black italic flex items-center gap-2">
            <CalendarRange size={18} className="text-nyt-accent" /> Машина на Времето
          </h2>
          <p className="text-[11px] text-muted-foreground uppercase font-black tracking-widest mt-1">Интензитет на вести: Последни 90 дена</p>
        </div>
        <div className="flex gap-4 text-xs font-bold font-sans">
          <div className="flex items-center gap-2"><span className="w-3 h-3 bg-nyt-accent/60 rounded-sm"></span> Волумен</div>
          <div className="flex items-center gap-2"><span className="w-3 h-3 bg-nyt-red/60 rounded-sm"></span> Итни развои</div>
        </div>
      </div>

      <div className="flex overflow-x-auto pb-12 hide-scrollbar -mx-2 px-2">
        <div className="flex gap-[3px] min-w-max items-end h-24">
          {grid.map((dayData, idx) => {
            const isBreakingDay = dayData.breaking_clusters > (maxBreaking * 0.3); // High breaking day
            const heightTotal = Math.max(10, (dayData.total_clusters / maxTotal) * 100);
            const intensity = getIntensityClass(
                isBreakingDay ? dayData.breaking_clusters : dayData.total_clusters, 
                isBreakingDay ? maxBreaking : maxTotal, 
                isBreakingDay
            );
            
            // Highlight every start of week/month or first item
            const d = new Date(dayData.day);
            const isMarker = idx === 0 || idx === grid.length - 1 || d.getDate() === 1;

            return (
              <a 
                key={dayData.day} 
                href={`/archive?date=${dayData.day}`}
                className="group flex flex-col items-center justify-end h-full gap-1"
                title={`${getLabel(dayData.day)}: ${dayData.total_clusters} вести, ${dayData.breaking_clusters} итни`}
              >
                <div 
                  className={`w-3 sm:w-4 rounded-sm transition-all hover:opacity-80 relative ${intensity}`}
                  style={{ height: `${heightTotal}%` }}
                >
                  {/* Tooltip on hover */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-foreground text-background text-[10px] font-bold py-1 px-2 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none transition-opacity z-10">
                    {getLabel(dayData.day)} • {dayData.total_clusters} објави
                  </div>
                </div>
                {/* Date marker below the bar */}
                <div className="h-6 flex items-center justify-center relative">
                    {isMarker && (
                      <span className="text-[8px] font-black text-muted-foreground uppercase opacity-70 absolute left-0 origin-left transform rotate-[60deg] mt-6 whitespace-nowrap">
                        {getLabel(dayData.day)}
                      </span>
                    )}
                </div>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
}
