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
      setError('Аналитичкиот центар е привремено недостапен.');
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
            <div key={i} className="mb-10">
                <span className="editorial-byline">Од уредничкиот тим на Пресек</span>
                <p className="mb-8 text-xl md:text-2xl leading-relaxed text-foreground font-serif italic border-l-4 border-nyt-accent pl-6 py-2 bg-secondary/5 rounded-r-lg drop-cap">
                    {parseBoldText(trimmed)}
                </p>
            </div>
          );
      }

      // Regular paragraphs
      return <p key={i} className="mb-6 text-lg md:text-xl leading-relaxed text-foreground/80 font-nyt-body">{parseBoldText(trimmed)}</p>;
    });
  };

  const modes = [
    { id: 'facts' as const, label: 'Бројки и факти', icon: BarChart3, desc: 'Статистика, клучни податоци и размер на настанот.' },
    { id: 'perspectives' as const, label: 'Ставови и изјави', icon: Users, desc: 'Клучни актери, цитати и спротивставени агли.' },
    { id: 'context' as const, label: 'Поширок контекст', icon: BookOpen, desc: 'Историска позадина и значење на развојот.' },
  ];

  return (
    <section className="research-analyst-container mt-12 mb-16 border border-border bg-card/50 p-5 md:p-6">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-2 flex items-center gap-2 font-sans text-[10px] font-black uppercase tracking-[0.18em] text-nyt-accent">
            <BrainCircuit size={14} strokeWidth={2} /> Аналитички Центар
          </p>
          <h2 className="font-serif text-2xl md:text-[2rem] font-black text-foreground mb-2">Подлабока анализа</h2>
          <p className="max-w-2xl font-nyt-body text-sm md:text-[15px] leading-relaxed text-secondary-foreground">
            Активирајте дополнителен аналитички слој само кога ви се потребни повеќе бројки, клучни актери или поширок контекст за приказната.
          </p>
        </div>
        <p className="max-w-sm font-sans text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground">
          Анализа по барање
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => performResearch(m.id)}
            disabled={!!loading}
            className={`group relative p-4 md:p-5 text-left border border-border bg-background transition-all hover:border-nyt-accent/30 hover:bg-secondary/10 ${loading === m.id ? 'border-nyt-accent bg-secondary/5' : ''}`}
          >
            <div className={`w-10 h-10 flex items-center justify-center rounded-lg mb-3 transition-colors ${loading === m.id ? 'bg-nyt-accent text-white' : 'bg-secondary text-muted-foreground group-hover:bg-nyt-accent group-hover:text-white'}`}>
              {loading === m.id ? <Loader2 className="animate-spin" size={20} /> : <m.icon size={20} />}
            </div>
            <h4 className="font-black text-[11px] mb-1 uppercase tracking-[0.12em] text-foreground group-hover:text-nyt-accent">{m.label}</h4>
            <p className="text-xs text-muted-foreground leading-relaxed font-medium">{m.desc}</p>
            <div className="mt-3 flex items-center text-[10px] font-black uppercase text-nyt-accent opacity-0 group-hover:opacity-100 transition-opacity">
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
        <div className="mt-8 editorial-panel p-0 overflow-hidden border border-nyt-accent/20 bg-background motion-rise">
          <div className="border-b border-nyt-accent/20 bg-nyt-accent/8 px-5 py-4 md:px-6 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles size={16} className="text-nyt-accent" fill="currentColor" />
              <span className="text-[11px] font-black uppercase tracking-[0.18em] text-foreground">
                {modes.find(m => m.id === data.mode)?.label}
              </span>
            </div>
            <button onClick={() => setData(null)} className="p-1 hover:bg-foreground/5 rounded-lg transition-colors">
                <X size={20} />
            </button>
          </div>
          
          <div className="p-5 md:p-8 relative">
             <div className="max-w-3xl">
                {formatText(data.report)}
             </div>
             
             <div className="mt-12 pt-6 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4 opacity-60">
                <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-widest">
                   <div className="w-2 h-2 rounded-full bg-nyt-accent animate-pulse"></div>
                   Интерна системска синтеза
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-[9px] font-black tracking-[0.24em] border border-foreground px-3 py-1.5 rounded-full">
                        СИСТЕМСКА ВЕРИФИКАЦИЈА
                    </span>
                </div>
             </div>
          </div>
        </div>
      )}
    </section>
  );
}
