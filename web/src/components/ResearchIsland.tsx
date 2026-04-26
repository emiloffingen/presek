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
        // Robust result mapping: handle 'answer' (research API), 'report' (analyst API), or raw string
        const report = result.report || result.answer || (typeof result === 'string' ? result : null);
        const suggestions = result.suggestions || [];
        const mode_actual = result.mode || mode;
        
        setData({ 
            report, 
            suggestions, 
            mode: mode_actual 
        });
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
    // 1. Handle Citations: (Извор: Name)
    const withCitations = text.replace(/\((Извор: .*?)\)/g, '<span class="citation-badge">$1</span>');
    
    // 2. Handle Bold: **text**
    const parts = withCitations.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-black text-foreground">{part.slice(2, -2)}</strong>;
      }
      if (part.includes('class="citation-badge"')) {
          const name = part.match(/>(.*)</)?.[1] || '';
          return <span key={i} className="inline-flex items-center px-1.5 py-0.5 mx-1 bg-secondary/80 border border-border rounded text-[9px] font-black text-nyt-accent uppercase tracking-tighter leading-none align-middle" title="Кредибилен извор">{name}</span>;
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

      // Headers (robust: matches '# Header' or '1. # Header')
      if (trimmed.includes('#')) {
          const headerText = trimmed.split('#')[1].trim();
          return <h3 key={i} className="font-serif font-black text-2xl mt-10 mb-6 border-b border-border pb-3 text-foreground tracking-tight">{parseBoldText(headerText)}</h3>;
      }
      
      // List items (robust: matches '-', '•', '*', '1. ', etc.)
      if (/^([-•*]|\d+\.)\s+/.test(trimmed)) {
          const cleanItem = trimmed.replace(/^([-•*]|\d+\.)\s+/, '');
          return (
            <div key={i} className="flex gap-4 mb-4 items-start pl-2">
              <span className="text-nyt-accent mt-1.5 flex-shrink-0"><CheckCircle2 size={16} strokeWidth={3} /></span>
              <span className="text-lg md:text-xl text-foreground/90 font-nyt-body leading-snug">{parseBoldText(cleanItem)}</span>
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
    <section className="research-analyst-container mt-16 mb-20 border-y md:border border-border bg-secondary/5 p-6 md:p-10 relative overflow-hidden">
      {/* Editorial Watermark */}
      <div className="absolute top-0 right-0 p-4 opacity-[0.03] pointer-events-none select-none">
          <Sparkles size={240} />
      </div>

      <div className="relative z-10 mb-10 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="max-w-3xl">
          <p className="mb-4 flex items-center gap-2 font-sans text-[11px] font-black uppercase tracking-[0.2em] text-nyt-accent">
            <div className="w-8 h-[2px] bg-nyt-accent"></div>
            ДОПОЛНИТЕЛНА АНАЛИТИКА
          </p>
          <h2 className="font-serif text-3xl md:text-[2.75rem] font-black text-foreground mb-4 leading-[1.1] tracking-tight">Истражувачки Центар</h2>
          <p className="font-serif text-lg md:text-xl leading-relaxed text-secondary-foreground italic opacity-90">
            Активирајте дополнителен истражувачки слој само кога ви се потребни повеќе бројки, клучни актери или поширок контекст за приказната.
          </p>
        </div>
        <div className="hidden md:block">
            <p className="font-sans text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground border-l-2 border-border pl-4 py-1">
            Увид по барање
            </p>
        </div>
      </div>

      <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-6">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => performResearch(m.id)}
            disabled={!!loading}
            className={`group relative p-6 text-left border border-border bg-background shadow-sm transition-all hover:shadow-xl hover:-translate-y-1 hover:border-nyt-accent/40 ${loading === m.id ? 'ring-2 ring-nyt-accent ring-inset border-transparent' : ''}`}
          >
            <div className={`w-12 h-12 flex items-center justify-center rounded-full mb-5 transition-all ${loading === m.id ? 'bg-nyt-accent text-white rotate-[360deg]' : 'bg-secondary text-muted-foreground group-hover:bg-nyt-accent group-hover:text-white'}`}>
              {loading === m.id ? <Loader2 className="animate-spin" size={24} /> : <m.icon size={22} />}
            </div>
            <h4 className="font-black text-xs mb-2 uppercase tracking-[0.14em] text-foreground group-hover:text-nyt-accent transition-colors">{m.label}</h4>
            <p className="text-[13px] text-muted-foreground leading-relaxed font-medium mb-6 min-h-[3rem]">{m.desc}</p>
            
            <div className="flex items-center justify-between pt-4 border-t border-border/50 group-hover:border-nyt-accent/30">
                <span className="text-[10px] font-black uppercase tracking-widest text-nyt-accent">Истражи</span>
                <ChevronRight size={14} className="text-nyt-accent group-hover:translate-x-1 transition-transform" />
            </div>
          </button>
        ))}
      </div>

      {/* Custom Research Input */}
      <div className="relative z-10 mt-8 flex flex-col md:flex-row gap-4 bg-background p-2 border border-border focus-within:border-nyt-accent/50 shadow-inner">
        <div className="relative flex-grow">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground opacity-50" size={20} />
            <input 
                type="text" 
                placeholder="Поставете конкретно прашање за овој настан..."
                value={customQuery}
                onChange={(e) => setCustomQuery(e.target.value)}
                className="w-full pl-12 pr-4 py-4 bg-transparent outline-none font-serif italic text-lg"
                onKeyDown={(e) => e.key === 'Enter' && customQuery && performResearch('custom', customQuery)}
            />
        </div>
        <button 
            onClick={() => performResearch('custom', customQuery)}
            disabled={!customQuery || !!loading}
            className="px-10 py-4 bg-foreground text-background font-black uppercase tracking-[0.2em] text-[10px] hover:bg-nyt-accent transition-all disabled:opacity-30 flex items-center justify-center gap-2"
        >
            {loading === 'custom' ? <Loader2 className="animate-spin" size={16} /> : (
                <>ИСТРАЖИ <ChevronRight size={12} /></>
            )}
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

                {/* Follow-up Suggestions */}
                {data.mode === 'custom' && data.suggestions && data.suggestions.length > 0 && (
                  <div className="mt-12 pt-8 border-t border-border/40">
                    <p className="font-sans text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent mb-6 flex items-center gap-2">
                      <ChevronRight size={12} strokeWidth={3} /> СЛЕДНО ИСТРАЖУВАЊЕ
                    </p>
                    <div className="flex flex-col gap-3">
                      {data.suggestions.map((s: string, idx: number) => (
                        <button 
                          key={idx}
                          onClick={() => {
                            setCustomQuery(s);
                            performResearch('custom', s);
                          }}
                          disabled={!!loading}
                          className="text-left p-4 border border-border bg-secondary/5 hover:border-nyt-accent hover:bg-secondary/10 transition-all font-serif italic text-lg text-foreground/90 group"
                        >
                          <span className="group-hover:translate-x-1 transition-transform inline-block">{s} →</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

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
                   Автоматизирана уредничка синтеза
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
