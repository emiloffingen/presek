import React, { useEffect, useState } from 'react';
import { Loader2, CalendarRange } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

interface HeatmapDay {
  day: string;
  total_clusters: number;
  breaking_clusters: number;
}

interface Props {
  selectedDate?: string;
  lang?: string;
}

export default function ArchiveHeatmapIsland({ selectedDate, lang = 'sr' }: Props) {
  const [data, setData] = useState<HeatmapDay[]>([]);
  const [loading, setLoading] = useState(true);
  const isMK = lang === 'mk';

  useEffect(() => {
    console.log('[ArchiveHeatmap] Fetching data...');
    fetch(`${apiBaseUrl()}/archive/heatmap?lang=${lang}`)
      .then(res => res.json())
      .then(json => {
        console.log('[ArchiveHeatmap] Data received:', json);
        if (json.status === 'success') {
          setData(json.data);
        }
      })
      .catch(err => {
        console.error('[ArchiveHeatmap] Fetch failed:', err);
      })
      .finally(() => setLoading(false));
  }, [lang]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-24 border border-dashed border-border rounded-lg">
        <Loader2 className="animate-spin text-nyt-accent mr-2" size={16} />
        <span className="text-xs text-muted-foreground uppercase font-black tracking-widest">
            {isMK ? 'Вчитување на машина на времето...' : 'Učitavanje mašine vremena...'}
        </span>
      </div>
    );
  }

  // Find max values for color scaling
  const maxTotal = data.length > 0 ? Math.max(...data.map(d => d.total_clusters), 1) : 1;
  const maxBreaking = data.length > 0 ? Math.max(...data.map(d => d.breaking_clusters), 1) : 1;

  // Fill in missing days to make a complete grid (last 180 days max, but trimmed to data start)
  const today = new Date();
  const rawGrid = [];
  for (let i = 179; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const existing = data.find(x => x.day === dateStr);
    rawGrid.push(existing || { day: dateStr, total_clusters: 0, breaking_clusters: 0 });
  }

  // Find the first day with any data and trim the grid to start from there (but at least last 60 days)
  const firstDataIdx = rawGrid.findIndex(d => d.total_clusters > 0);
  const minDays = 60;
  const startIdx = firstDataIdx === -1 ? (rawGrid.length - minDays) : Math.min(firstDataIdx, rawGrid.length - minDays);
  const grid = rawGrid.slice(startIdx);

  if (data.length === 0) {
    return (
      <div className="flex justify-center items-center h-24 border border-dashed border-border rounded-lg bg-secondary/5">
        <span className="text-[10px] text-muted-foreground uppercase font-black tracking-[0.2em]">
            {isMK ? 'Нема податоци за овој период' : 'Nema podataka za ovaj period'}
        </span>
      </div>
    );
  }

  const getIntensityClass = (count: number, max: number, isBreaking: boolean) => {
    if (count === 0) return 'bg-muted/20 border border-border/10';
    const ratio = count / max;
    if (isBreaking) {
      if (ratio > 0.6) return 'bg-nyt-red text-white shadow-[0_0_8px_rgba(185,28,28,0.3)]';
      if (ratio > 0.2) return 'bg-nyt-red/70';
      return 'bg-nyt-red/40';
    } else {
      if (ratio > 0.6) return 'bg-nyt-accent text-white shadow-[0_0_8px_rgba(30,64,175,0.3)]';
      if (ratio > 0.2) return 'bg-nyt-accent/70';
      return 'bg-nyt-accent/40';
    }
  };

  const getLabel = (dateStr: string) => {
    const d = new Date(dateStr.replace("Z", ""));
    return d.toLocaleDateString(isMK ? 'mk-MK' : 'sr-RS', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-6 mb-8 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-[var(--grid-gap)] mb-6">
        <div>
          <h2 className="font-serif text-xl font-black italic flex items-center gap-[var(--grid-gap)]">
            <CalendarRange size={18} className="text-nyt-accent" /> {isMK ? 'Машина на Времето' : 'Mašina Vremena'}
          </h2>
          <p className="text-[11px] text-muted-foreground uppercase font-black tracking-widest mt-1">
              {isMK ? 'Интензитет на вести: Последни 180 дена' : 'Intenzitet vesti: Poslednjih 180 dana'}
          </p>
        </div>
        <div className="flex gap-[var(--grid-gap)] text-xs font-bold font-sans">
          <div className="flex items-center gap-[var(--grid-gap)]"><span className="w-3 h-3 bg-nyt-accent/60 rounded-sm"></span> {isMK ? 'Волумен' : 'Volumen'}</div>
          <div className="flex items-center gap-[var(--grid-gap)]"><span className="w-3 h-3 bg-nyt-red/60 rounded-sm"></span> {isMK ? 'Итни развои' : 'Hitni razvoji'}</div>
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
            const isActive = dayData.day === selectedDate;

            return (
              <a
                key={dayData.day}
                href={`${isMK ? '/mk' : ''}/archive?date=${dayData.day}`}
                className={`group flex flex-col items-center justify-end h-full gap-1 ${isActive ? 'scale-110 z-20' : ''}`}
                title={`${getLabel(dayData.day)}: ${dayData.total_clusters} ${isMK ? 'вести' : 'vesti'}, ${dayData.breaking_clusters} ${isMK ? 'итни' : 'hitni'}`}
              >
                <div
                  className={`w-3 sm:w-4 rounded-sm transition-all hover:opacity-80 relative ${intensity} ${isActive ? 'ring-2 ring-foreground ring-offset-2 ring-offset-background' : ''}`}
                  style={{ height: `${heightTotal}%` }}
                >
                  {/* Tooltip on hover */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-foreground text-background text-[10px] font-bold py-1 px-2 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none transition-opacity z-10">
                    {getLabel(dayData.day)} • {dayData.total_clusters} {isMK ? 'објави' : 'objave'}
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
