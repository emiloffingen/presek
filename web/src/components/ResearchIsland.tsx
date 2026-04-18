import React, { useState } from 'react';
import { Sparkles, BrainCircuit, BarChart3, Users, BookOpen, Loader2, X, CheckCircle2, ChevronRight } from 'lucide-react';

interface ResearchIslandProps {
  clusterId: string;
  initialHeadline: string;
}

type ResearchMode = 'facts' | 'perspectives' | 'context';

export default function ResearchIsland({ clusterId, initialHeadline }: ResearchIslandProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<ResearchMode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const performResearch = async (mode: ResearchMode) => {
    setLoading(mode);
    setError(null);
    try {
      const resp = await fetch(`/api/intelligence/cluster/${clusterId}/analyst?mode=${mode}`);
      const result = await resp.json();
      if (result.status === 'success') {
        setData(result);
      } else {
        setError(result.message || 'Грешка при анализата.');
      }
    } catch (e) {
      setError('Аналитичарот моментално не е достапен.');
    } finally {
      setLoading(null);
    }
  };

  const parseBoldText = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-black text-foreground">{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  const formatText = (text: string) => {
    if (!text) return '';
    const lines = text.split('\n').filter(l => l.trim() !== '');
    
    return lines.map((line, i) => {
      const trimmed = line.trim();
      
      // Headers
      if (trimmed.startsWith('#')) {
          return <h3 key={i} className="font-serif font-black text-2xl mt-10 mb-6 border-b border-border pb-3 text-foreground tracking-tight">{parseBoldText(trimmed.replace(/^#+\s*/, ''))}</h3>;
      }
      
      // List items
      if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
          return (
            <div key={i} className="flex gap-4 mb-4 items-start pl-2">
              <span className="text-nyt-accent mt-1.5 flex-shrink-0"><CheckCircle2 size={16} strokeWidth={3} /></span>
              <span className="text-lg md:text-xl text-foreground/90 font-nyt-body leading-snug">{parseBoldText(trimmed.replace(/^[-•]\s*/, ''))}</span>
            </div>
          );
      }

      // First paragraph (Drop Cap style)
      if (i === 0) {
          return (
            <p key={i} className="mb-8 text-xl md:text-2xl leading-relaxed text-foreground font-serif italic border-l-4 border-nyt-accent pl-6 py-2 bg-secondary/5 rounded-r-lg">
                {parseBoldText(trimmed)}
            </p>
          );
      }

      // Regular paragraphs
      return <p key={i} className="mb-6 text-lg md:text-xl leading-relaxed text-foreground/80 font-nyt-body">{parseBoldText(trimmed)}</p>;
    });
  };

  const modes = [
    { id: 'facts' as const, label: 'Бројки и Факти', icon: BarChart3, desc: 'Клучни статистички податоци.' },
    { id: 'perspectives' as const, label: 'Ставови и Изјави', icon: Users, desc: 'Анализа на актери и цитати.' },
    { id: 'context' as const, label: 'Широк Контекст', icon: BookOpen, desc: 'Позадина и општествено влијание.' },
  ];

  return (
    <div className="ai-analyst-container mt-16 mb-24 max-w-4xl mx-auto">
      <div className="flex flex-col items-center text-center mb-10">
        <div className="p-4 bg-nyt-accent/10 rounded-full text-nyt-accent mb-4">
            <BrainCircuit size={32} strokeWidth={1.5} />
        </div>
        <h2 className="font-serif font-black text-3xl md:text-4xl text-foreground mb-2">Интелигенција на Пресек</h2>
        <p className="text-muted-foreground text-sm uppercase tracking-[0.2em] font-black">AI Истражувачки Центар</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => performResearch(m.id)}
            disabled={!!loading}
            className={`group relative p-6 text-left border-2 border-border rounded-2xl bg-background transition-all hover:border-nyt-accent/40 hover:shadow-2xl ${loading === m.id ? 'border-nyt-accent bg-secondary/5' : ''}`}
          >
            <div className={`w-12 h-12 flex items-center justify-center rounded-xl mb-6 transition-colors ${loading === m.id ? 'bg-nyt-accent text-white' : 'bg-secondary text-muted-foreground group-hover:bg-nyt-accent group-hover:text-white'}`}>
              {loading === m.id ? <Loader2 className="animate-spin" size={24} /> : <m.icon size={24} />}
            </div>
            <h4 className="font-black text-xs mb-3 uppercase tracking-widest text-foreground group-hover:text-nyt-accent">{m.label}</h4>
            <p className="text-xs text-muted-foreground leading-relaxed font-medium">{m.desc}</p>
            <div className="mt-6 flex items-center text-[10px] font-black uppercase text-nyt-accent opacity-0 group-hover:opacity-100 transition-opacity">
                Истражи <ChevronRight size={10} className="ml-1" />
            </div>
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-8 p-5 border-2 border-red-500/20 bg-red-500/5 text-red-600 dark:text-red-400 text-sm font-bold rounded-xl flex justify-between items-center">
          <div className="flex items-center gap-3">
             <X size={18} />
             <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="uppercase text-[10px] tracking-widest underline">Затвори</button>
        </div>
      )}

      {data && (
        <div className="mt-12 editorial-panel p-0 overflow-hidden border-2 border-nyt-accent/20 bg-background motion-rise shadow-[0_30px_60px_-12px_rgba(0,0,0,0.25)] rounded-3xl">
          <div className="bg-nyt-accent text-white px-8 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles size={16} fill="currentColor" />
              <span className="text-xs font-black uppercase tracking-[0.2em]">
                {modes.find(m => m.id === data.mode)?.label} · Специјален Извештај
              </span>
            </div>
            <button onClick={() => setData(null)} className="p-1 hover:bg-white/20 rounded-lg transition-colors">
                <X size={20} />
            </button>
          </div>
          
          <div className="p-8 md:p-16 relative">
             <div className="max-w-3xl mx-auto">
                {formatText(data.report)}
             </div>
             
             <div className="mt-16 pt-10 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-6 opacity-60">
                <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-widest">
                   <div className="w-2 h-2 rounded-full bg-nyt-accent animate-pulse"></div>
                   Интерна синтеза на целосна содржина
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-[9px] font-black tracking-[0.3em] border-2 border-foreground px-3 py-1.5 rounded-full">
                        MISTRAL ANALYST 4.0
                    </span>
                </div>
             </div>
          </div>
        </div>
      )}
    </div>
  );
}
