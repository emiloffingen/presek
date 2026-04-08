import React, { useState, useEffect } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { ArrowLeftRight, Loader2, Info } from 'lucide-react';

interface SourceMetrics {
  source: string;
  avg_sentiment: number;
  avg_objectivity: number;
  avg_sensationalism: number;
  cluster_count: number;
}

export default function SourceComparisonIsland({ allSources }: { allSources: string[] }) {
  const [s1, setS1] = useState(allSources[0] || '');
  const [s2, setS2] = useState(allSources[1] || '');
  const [metrics, setMetrics] = useState<SourceMetrics[]>([]);
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
    const p1 = Math.round(val1 * 100);
    const p2 = Math.round(val2 * 100);
    
    // For inverse (sensationalism), lower is better/accented
    const isWinner1 = inverse ? p1 < p2 : p1 > p2;
    const isWinner2 = inverse ? p2 < p1 : p2 > p1;

    return (
      <div className="space-y-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground text-center">{label}</p>
        <div className="flex items-center gap-4">
          <div className="flex-1 text-right">
            <span className={`font-serif font-black text-xl ${isWinner1 ? 'text-nyt-accent' : 'text-foreground/60'}`}>{p1}%</span>
          </div>
          <div className="flex-[2] h-2 bg-secondary rounded-full overflow-hidden flex">
            <div className="h-full bg-nyt-accent/40 border-r border-background" style={{ width: `${p1}%` }} />
            <div className="h-full bg-nyt-red/40" style={{ width: `${p2}%` }} />
          </div>
          <div className="flex-1 text-left">
            <span className={`font-serif font-black text-xl ${isWinner2 ? 'text-nyt-red' : 'text-foreground/60'}`}>{p2}%</span>
          </div>
        </div>
      </div>
    );
  };

  const m1 = metrics.find(m => m.source === s1);
  const m2 = metrics.find(m => m.source === s2);

  return (
    <section className="rail-module border border-border p-8 rounded-xl bg-card">
      <div className="flex items-center justify-between mb-8">
        <h2 className="font-serif text-2xl font-black italic">Споредба на медиуми</h2>
        <ArrowLeftRight size={20} className="text-nyt-accent" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
        <select 
          value={s1} 
          onChange={e => setS1(e.target.value)}
          className="bg-secondary/50 border border-border rounded-lg px-4 py-2 font-serif font-bold text-sm focus:outline-none focus:border-nyt-accent"
        >
          {allSources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select 
          value={s2} 
          onChange={e => setS2(e.target.value)}
          className="bg-secondary/50 border border-border rounded-lg px-4 py-2 font-serif font-bold text-sm focus:outline-none focus:border-nyt-accent"
        >
          {allSources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="py-12 flex justify-center"><Loader2 className="animate-spin text-nyt-accent" /></div>
      ) : m1 && m2 ? (
        <div className="space-y-8">
          {renderMetric("Индекс на Објективност", m1.avg_objectivity, m2.avg_objectivity)}
          {renderMetric("Сензационализам (Clickbait)", m1.avg_sensationalism, m2.avg_sensationalism, true)}
          
          <div className="pt-6 border-t border-border flex justify-between gap-4">
            <div className="text-center flex-1">
                <p className="text-[9px] font-black uppercase tracking-tighter text-muted-foreground mb-1">{s1}</p>
                <strong className="text-xs">{m1.cluster_count} вести анализирани</strong>
            </div>
            <div className="text-center flex-1">
                <p className="text-[9px] font-black uppercase tracking-tighter text-muted-foreground mb-1">{s2}</p>
                <strong className="text-xs">{m2.cluster_count} вести анализирани</strong>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-12 text-center text-muted-foreground italic font-serif">
          Изберете два медиуми за да ја започнете анализата.
        </div>
      )}
    </section>
  );
}
