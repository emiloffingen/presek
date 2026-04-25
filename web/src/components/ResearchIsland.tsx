import React, { useState } from 'react';
import { Sparkles, BrainCircuit, BarChart3, Users, BookOpen, Loader2, X, CheckCircle2, ChevronRight, Search } from 'lucide-react';

interface ResearchIslandProps {
  clusterId: string;
  initialHeadline: string;
  sources?: string[];
}

type ResearchMode = 'facts' | 'perspectives' | 'context';

export default function ResearchIsland({ clusterId, initialHeadline, sources = [] }: ResearchIslandProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<ResearchMode | 'custom' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customQuery, setCustomQuery] = useState('');

  const performResearch = async (mode: ResearchMode | 'custom', query?: string) => {
    setLoading(mode);
    setError(null);
    try {
      let url = `/api/intelligence/cluster/${clusterId}/analyst?mode=${mode}`;
      if (mode === 'custom') {
          url = `/api/research/${clusterId}?q=${encodeURIComponent(query || '')}`;
      }
      
      const resp = await fetch(url);
      const result = await resp.json();
      if (result.status === 'success') {
        // Map research API 'answer' to 'report' for consistency with existing UI
        if (mode === 'custom') {
            setData({ report: result.answer, mode: 'custom' });
        } else {
            setData(result);
        }
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
      
      // Pull Quotes Detection
      if ((trimmed.startsWith('„') && trimmed.endsWith('“')) || (trimmed.startsWith('"') && trimmed.endsWith('"'))) {
          return (
            <div key={i} className="my-12 py-8 border-y-2 border-double border-border text-center">
                <blockquote className="font-serif italic text-2xl md:text-3xl text-foreground/90 leading-tight px-4">
                    {parseBoldText(trimmed)}
                </blockquote>
            </div>
          );
      }

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

      {/* Custom Research Input */}
      <div className="mt-6 flex flex-col md:flex-row gap-3">
        <div className="relative flex-grow">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
            <input 
                type="text" 
                placeholder="Поставете конкретно прашање за овој настан..."
                value={customQuery}
                onChange={(e) => setCustomQuery(e.target.value)}
                className="w-full pl-12 pr-4 py-4 bg-background border border-border focus:border-nyt-accent outline-none font-nyt-body text-lg shadow-inner"
                onKeyDown={(e) => e.key === 'Enter' && customQuery && performResearch('custom', customQuery)}
            />
        </div>
        <button 
            onClick={() => performResearch('custom', customQuery)}
            disabled={!customQuery || !!loading}
            className="px-8 py-4 bg-foreground text-background font-black uppercase tracking-widest text-xs hover:bg-nyt-accent transition-colors disabled:opacity-50"
        >
            {loading === 'custom' ? <Loader2 className="animate-spin" size={18} /> : 'Истражи'}
        </button>
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
          <div className="border-b border-nyt-accent/20 bg-nyt-accent/8 px-5 py-4 md:px-6 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles size={16} className="text-nyt-accent" fill="currentColor" />
              <span className="text-[11px] font-black uppercase tracking-[0.18em] text-foreground">
                {data.mode === 'custom' ? 'Одговор на истражувањето' : modes.find(m => m.id === data.mode)?.label}
              </span>
            </div>

            {/* Complexity Meter */}
            <div className="flex items-center gap-2 py-1 px-3 bg-background/50 rounded border border-nyt-accent/10">
                <span className="text-[8px] font-black uppercase tracking-wider text-muted-foreground">Комплексност:</span>
                <div className="flex gap-1">
                    {[1, 2, 3].map((step) => {
                        const content = String(data.report || '').toLowerCase();
                        const level = (content.includes('разлики') || content.includes('контрадикторни')) ? 3 : 
                                      (content.includes('дел од изворите') || content.includes('нејасно')) ? 2 : 1;
                        const isActive = step <= level;
                        const color = level === 3 ? 'bg-nyt-red' : level === 2 ? 'bg-amber-500' : 'bg-emerald-600';
                        return <div key={step} className={`w-3 h-1 rounded-full transition-colors ${isActive ? color : 'bg-border'}`} />
                    })}
                </div>
            </div>

            <button onClick={() => setData(null)} className="p-1 hover:bg-foreground/5 rounded-lg transition-colors ml-auto">
                <X size={20} />
            </button>
          </div>
          
          <div className="p-5 md:p-8 relative">
             <div className="max-w-3xl">
                {formatText(data.report)}

                {sources.length > 0 && (
                  <div className="mt-16 pt-8 border-t border-border/40">
                    <p className="font-sans text-[9px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4">
                      РЕДАКЦИИ КОНСУЛТИРАНИ ЗА ОВАА СИНТЕЗА
                    </p>
                    <div className="flex flex-wrap gap-x-4 gap-y-2">
                      {[...new Set(sources)].map((s, idx, arr) => (
                        <span key={s} className="font-sans text-[10px] font-extrabold text-foreground/70 uppercase tracking-wider flex items-center">
                          {s}
                          {idx < arr.length - 1 && <span className="ml-4 opacity-30 text-muted-foreground">•</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
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
