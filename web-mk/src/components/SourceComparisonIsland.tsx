import React, { useState, useEffect } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { ArrowLeftRight, Loader2 } from 'lucide-react';

interface SourceMetrics {
  source: string;
  avg_sentiment: number;
  avg_objectivity: number;
  avg_sensationalism: number;
  cluster_count: number;
}

interface OverlapMetrics {
  shared_clusters: number;
  s1_exclusive: number;
  s2_exclusive: number;
}

export default function SourceComparisonIsland({ allSources }: { allSources: string[] }) {
  const [s1, setS1] = useState(allSources[0] || '');
  const [s2, setS2] = useState(allSources[1] || '');
  const [metrics, setMetrics] = useState<SourceMetrics[]>([]);
  const [overlap, setOverlap] = useState<OverlapMetrics | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    if (!s1 || !s2) return;
    setLoading(true);
    try {
      const API_URL = apiBaseUrl();
      const res = await fetch(`${API_URL}/intelligence/compare-sources?s1=${encodeURIComponent(s1)}&s2=${encodeURIComponent(s2)}`);
      const json = await res.json();
      if (json.status === 'success') {
        setMetrics(json.data);
        setOverlap(json.overlap);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [s1, s2]);

  const renderMetric = (label: string, val1: number, val2: number, inverse = false) => {
    const p1 = Math.max(0, Math.min(100, Math.round((Number(val1) || 0) * 100)));
    const p2 = Math.max(0, Math.min(100, Math.round((Number(val2) || 0) * 100)));

    const tooltip = label === "Индекс на објективност"
      ? "Мерка за непристрасност и присуство на фактички верификувани изјави."
      : "Ниво на емотивен набој и употреба на реторика за привлекување внимание.";

    const isWinner1 = inverse ? p1 < p2 : p1 > p2;
    const isWinner2 = inverse ? p2 < p1 : p2 > p1;

    return (
      <div className="space-y-4">
        <p className="text-[11px] font-black uppercase tracking-[0.15em] text-muted-foreground text-center" title={tooltip}>{label}</p>
        <div className="flex items-center gap-6">
          <div className="flex-1 text-right">
            <span className={`font-serif font-black text-3xl tabular-nums ${isWinner1 ? 'text-nyt-accent' : 'text-foreground/40'}`}>{p1}%</span>
          </div>
          <div className="flex-[2] h-1.5 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden flex shadow-inner">
            <div className={`h-full transition-all duration-1000 ${isWinner1 ? 'bg-nyt-accent' : 'bg-zinc-400'}`} style={{ width: `${p1}%` }} />
            <div className="w-px h-full bg-background z-10" />
            <div className={`h-full transition-all duration-1000 ${isWinner2 ? 'bg-nyt-red' : 'bg-zinc-400'}`} style={{ width: `${p2}%` }} />
          </div>
          <div className="flex-1 text-left">
            <span className={`font-serif font-black text-3xl tabular-nums ${isWinner2 ? 'text-nyt-red' : 'text-foreground/40'}`}>{p2}%</span>
          </div>
        </div>
      </div>
    );
  };

  const m1 = metrics.find(m => m.source === s1);
  const m2 = metrics.find(m => m.source === s2);

  return (
    <section className="rail-module border border-zinc-200 dark:border-zinc-800 p-8 md:p-10 rounded-xl bg-background shadow-sm">
      <div className="flex items-center justify-between mb-10">
        <h2 className="font-serif text-2xl font-black tracking-tight italic border-b-4 border-nyt-accent pb-1">Споредба на редакции</h2>
        <div className="p-2 bg-secondary/50 rounded-full">
            <ArrowLeftRight size={20} className="text-nyt-accent" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
        <div className="space-y-2">
            <label className="text-[9px] font-black uppercase tracking-widest text-muted-foreground ml-1">Прв извор</label>
            <select 
            value={s1} 
            onChange={e => setS1(e.target.value)}
            className="w-full bg-secondary/30 border border-border rounded-lg px-4 py-3 font-serif font-black text-base focus:outline-none focus:ring-2 focus:ring-nyt-accent/20 transition-all appearance-none"
            style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'currentColor\'%3E%3Cpath stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'2\' d=\'M19 9l-7 7-7-7\' /%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', backgroundSize: '1.2em' }}
            >
            {allSources.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
        </div>
        <div className="space-y-2">
            <label className="text-[9px] font-black uppercase tracking-widest text-muted-foreground ml-1">Втор извор</label>
            <select 
            value={s2} 
            onChange={e => setS2(e.target.value)}
            className="w-full bg-secondary/30 border border-border rounded-lg px-4 py-3 font-serif font-black text-base focus:outline-none focus:ring-2 focus:ring-nyt-red/20 transition-all appearance-none"
            style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'currentColor\'%3E%3Cpath stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'2\' d=\'M19 9l-7 7-7-7\' /%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', backgroundSize: '1.2em' }}
            >
            {allSources.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
        </div>
      </div>

      {loading ? (
        <div className="py-20 flex flex-col items-center gap-4">
            <Loader2 className="animate-spin text-nyt-accent" size={32} />
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">Калкулирање на метрики...</p>
        </div>
      ) : m1 && m2 ? (
        <div className="space-y-12">
          {renderMetric("Индекс на објективност", m1.avg_objectivity, m2.avg_objectivity)}
          {renderMetric("Сензационализам", m1.avg_sensationalism, m2.avg_sensationalism, true)}
          
          {overlap && (
            <div className="space-y-5 pt-6 border-t border-zinc-100 dark:border-zinc-800">
              <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground text-center">Тематско преклопување</p>
              
              <div className="flex w-full h-10 rounded-xl overflow-hidden border-2 border-zinc-100 dark:border-zinc-800 shadow-sm p-1 gap-1">
                {(() => {
                  const totalOverlap = Math.max(1, overlap.shared_clusters + overlap.s1_exclusive + overlap.s2_exclusive);
                  return (
                    <>
                      <div
                        className="h-full bg-nyt-accent rounded-l-lg flex flex-col items-center justify-center text-white transition-all hover:brightness-110"
                        style={{ width: `${Math.max((overlap.s1_exclusive / totalOverlap) * 100, 10)}%` }}
                      >
                        <span className="text-[13px] font-black leading-none">{overlap.s1_exclusive}</span>
                      </div>
                      <div
                        className="h-full bg-zinc-200 dark:bg-zinc-700 flex flex-col items-center justify-center text-zinc-600 dark:text-zinc-300 transition-all hover:bg-zinc-300 dark:hover:bg-zinc-600"
                        style={{ width: `${Math.max((overlap.shared_clusters / totalOverlap) * 100, 20)}%` }}
                      >
                        <span className="text-[11px] font-black leading-none">{overlap.shared_clusters}</span>
                        <span className="text-[7px] font-black uppercase mt-0.5">заеднички</span>
                      </div>
                      <div
                        className="h-full bg-nyt-red rounded-r-lg flex flex-col items-center justify-center text-white transition-all hover:brightness-110"
                        style={{ width: `${Math.max((overlap.s2_exclusive / totalOverlap) * 100, 10)}%` }}
                      >
                        <span className="text-[13px] font-black leading-none">{overlap.s2_exclusive}</span>
                      </div>
                    </>
                  );
                })()}
              </div>
              
              <div className="flex justify-between text-[10px] font-black uppercase tracking-tighter text-zinc-500 px-1">
                  <span className="w-1/3 truncate" title={s1}>{s1} сам</span>
                  <span className="w-1/3 text-center">Споделен интерес</span>
                  <span className="w-1/3 text-right truncate" title={s2}>{s2} сам</span>
              </div>
            </div>
          )}

          <div className="pt-8 border-t border-zinc-200 dark:border-zinc-800 flex justify-between gap-6">
            <div className="text-center flex-1 p-4 bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-zinc-100 dark:border-zinc-800">
                <p className="text-[10px] font-black uppercase tracking-widest text-nyt-accent mb-2">{s1}</p>
                <div className="flex items-baseline justify-center gap-1">
                    <span className="text-2xl font-black tabular-nums">{m1.cluster_count}</span>
                    <span className="text-[10px] font-bold text-muted-foreground">вести</span>
                </div>
            </div>
            <div className="text-center flex-1 p-4 bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-zinc-100 dark:border-zinc-800">
                <p className="text-[10px] font-black uppercase tracking-widest text-nyt-red mb-2">{s2}</p>
                <div className="flex items-baseline justify-center gap-1">
                    <span className="text-2xl font-black tabular-nums">{m2.cluster_count}</span>
                    <span className="text-[10px] font-bold text-muted-foreground">вести</span>
                </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-20 text-center text-muted-foreground italic font-serif opacity-60">
          Изберете две редакции за детална анализа на нивниот уреднички пристап.
        </div>
      )}
    </section>
  );
