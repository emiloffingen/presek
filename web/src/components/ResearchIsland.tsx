import React, { useState } from 'react';
import { Sparkles, BrainCircuit, Search, Loader2, ChevronRight, AlertCircle, ExternalLink } from 'lucide-react';

interface ResearchIslandProps {
  clusterId: string;
  initialHeadline: string;
}

export default function ResearchIsland({ clusterId, initialHeadline }: ResearchIslandProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const performResearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`/api/intelligence/cluster/${clusterId}/research`);
      const result = await resp.json();
      if (result.status === 'success') {
        setData(result);
      } else {
        setError(result.message || 'Грешка при истражувањето.');
      }
    } catch (e) {
      setError('Моментално не можеме да пристапиме до AI истражувачот.');
    } finally {
      setLoading(false);
    }
  };

  const formatText = (text: string) => {
    if (!text) return '';
    // Basic formatting for the AI response
    return text.split('\n').map((line, i) => {
      if (line.match(/^\d\./) || line.startsWith('1.') || line.startsWith('2.')) {
          return <h4 key={i} className="text-sm font-black uppercase tracking-widest text-nyt-accent mt-6 mb-3">{line}</h4>;
      }
      if (line.trim().startsWith('-') || line.trim().startsWith('•')) {
          return <li key={i} className="ml-4 mb-2 text-sm leading-relaxed opacity-90 list-disc">{line.replace(/^[-•]\s*/, '')}</li>;
      }
      if (line.trim() === '') return <div key={i} className="h-2" />;
      return <p key={i} className="mb-3 text-sm leading-relaxed opacity-90">{line}</p>;
    });
  };

  return (
    <div className="ai-research-container mt-12 mb-16">
      {!data && !loading && (
        <button 
          onClick={performResearch}
          className="w-full group relative overflow-hidden rounded-xl border border-border bg-secondary/20 p-8 text-left transition-all hover:bg-secondary/40 hover:border-nyt-accent/30"
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-5">
              <div className="p-4 bg-nyt-accent/10 rounded-2xl text-nyt-accent group-hover:scale-110 transition-transform duration-300">
                <BrainCircuit size={32} strokeWidth={1.5} />
              </div>
              <div>
                <h3 className="font-serif font-black text-xl md:text-2xl text-foreground mb-2 flex items-center gap-2">
                  Сакате подлабока анализа?
                </h3>
                <p className="text-muted-foreground text-sm max-w-lg leading-relaxed">
                  Нашиот AI Истражувач може да пребара на Google за да најде клучни бројки, реакции и поширок контекст што можеби недостасува во овие вести.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 font-black uppercase text-[10px] tracking-widest text-nyt-accent bg-background px-4 py-3 rounded-full border border-nyt-accent/20 group-hover:bg-nyt-accent group-hover:text-white transition-colors">
              Прашај го AI Истражувачот <ChevronRight size={12} />
            </div>
          </div>
          
          {/* Subtle background glow */}
          <div className="absolute -right-20 -bottom-20 w-64 h-64 bg-nyt-accent/5 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </button>
      )}

      {loading && (
        <div className="editorial-panel p-12 text-center border-nyt-accent/20 bg-secondary/10">
          <div className="relative inline-block mb-6">
            <Loader2 className="animate-spin text-nyt-accent" size={48} strokeWidth={1} />
            <Search className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-nyt-accent/40" size={16} />
          </div>
          <h3 className="font-serif italic text-xl mb-2">AI Истражувачот пребарува на Google...</h3>
          <p className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">Ги анализираме најновите факти и реакции</p>
        </div>
      )}

      {error && (
        <div className="editorial-panel p-6 border-red-500/20 bg-red-500/5 flex items-center gap-4 text-red-600 dark:text-red-400">
          <AlertCircle size={20} />
          <p className="text-sm font-bold">{error}</p>
          <button onClick={performResearch} className="ml-auto text-[10px] underline uppercase tracking-widest">Обиди се пак</button>
        </div>
      )}

      {data && (
        <div className="editorial-panel p-0 overflow-hidden border-nyt-accent/30 motion-rise">
          <div className="bg-nyt-accent px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-white">
              <Sparkles size={14} fill="currentColor" />
              <span className="text-[10px] font-black uppercase tracking-[0.2em]">Deep AI Research</span>
            </div>
            <span className="text-[9px] text-white/70 font-bold uppercase">Powered by Gemini 2.0 & Google Search</span>
          </div>
          
          <div className="p-8 md:p-12 bg-background/50">
             <div className="prose-nyt max-w-none">
                {formatText(data.research)}
             </div>
             
             <div className="mt-10 pt-8 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground italic">
                   Извор: Анализа на глобални податоци во реално време.
                </div>
                <button 
                  onClick={() => setData(null)}
                  className="text-[10px] font-black uppercase tracking-widest opacity-60 hover:opacity-100 transition-opacity"
                >
                  Затвори истражување
                </button>
             </div>
          </div>
        </div>
      )}
    </div>
  );
}
