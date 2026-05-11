import React, { useState, useEffect, useRef } from 'react';
import { Sparkles, BarChart3, Users, BookOpen, Loader2, X, CheckCircle2, ChevronRight, Search } from 'lucide-react';

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

  const resultsRef = useRef<HTMLDivElement>(null);
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const placeholders = [
      "Sto sakate da doznaete za ova prica?",
      "Koj e glavni konflikt?",
      "Sto velat brojkite?",
      "Kakvi se reakciite?"
  ];

  useEffect(() => {
      const interval = setInterval(() => {
          setPlaceholderIdx((prev) => (prev + 1) % placeholders.length);
      }, 4000);
      return () => clearInterval(interval);
  }, []);

  useEffect(() => {
      if (data && resultsRef.current) {
          // Delay slightly to allow DOM to render
          setTimeout(() => {
              resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }, 100);
      }
  }, [data]);

  const performResearch = async (mode: ResearchMode | 'custom', query?: string) => {
    setLoading(mode);
    setError(null);
    try {
      const params = new URLSearchParams({ mode });
      if (mode === 'custom') params.set('q', query || '');
      const url = `/api/intelligence/cluster/${clusterId}/research?${params.toString()}`;
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 120s limit

      const resp = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);

      const result = await resp.json();
      if (!resp.ok) {
        setError(result?.message || result?.detail || 'Istrazuvanjeto momentalno ne e dostapno.');
      } else if (result.status === 'success') {
        // Robust result mapping: handle 'answer' (research API), 'report' (analyst API), or raw string
        const report = result.report || result.answer || (typeof result === 'string' ? result : null);
        const suggestions = result.suggestions || [];
        const mode_actual = result.mode || mode;
        
        setData({ 
            report, 
            suggestions, 
            mode: mode_actual,
            provider: result.provider,
            sources: result.sources || sources,
        });
      } else {
        setError(result.message || 'Greska pri analizata.');
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
          setError('Baranjeto traese predolgo. Obidete se povtorno za nekolku sekundi.');
      } else {
          setError('Analitickiot centar e privremeno nedostapen.');
      }
    } finally {
      setLoading(null);
    }
  };

  const parseBoldText = (text: string) => {
    if (!text) return null;
    
    const cleanText = text.replace(/\\n/g, '\n');
    const boldRegex = /\*\*(.*?)\*\*/g;
    
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = boldRegex.exec(cleanText)) !== null) {
      if (match.index > lastIndex) {
        parts.push(cleanText.substring(lastIndex, match.index));
      }
      parts.push(<strong key={match.index} className="font-black text-foreground">{match[1]}</strong>);
      lastIndex = boldRegex.lastIndex;
    }

    if (lastIndex < cleanText.length) {
      parts.push(cleanText.substring(lastIndex));
    }

    return parts.length > 0 ? parts : cleanText;
  };

  const formatText = (text: string) => {
    if (!text) return '';
    const lines = text.split('\n').filter(l => l.trim() !== '');
    
    return lines.map((line, i) => {
      const trimmed = line.trim();
      const animStyle = { animationDelay: `${i * 150}ms` };
      const animClass = "animate-in fade-in slide-in-from-bottom-4 duration-700 fill-mode-both break-words";
      
      // Pull Quotes Detection
      if ((trimmed.startsWith('„') && trimmed.endsWith('“')) || (trimmed.startsWith('"') && trimmed.endsWith('"'))) {
          return (
            <div key={i} className={`my-8 md:my-12 py-6 md:py-8 border-y-2 border-double border-border text-center ${animClass}`} style={animStyle}>
                <blockquote className="font-serif italic text-xl md:text-3xl text-foreground/90 leading-tight px-2 md:px-4">
                    {parseBoldText(trimmed)}
                </blockquote>
            </div>
          );
      }

      // Headers (robust: matches '# Header' or '1. # Header')
      if (trimmed.includes('#')) {
          const headerText = trimmed.split('#')[1].trim();
          return <h3 key={i} className={`font-serif font-black text-2xl md:text-3xl mt-12 mb-6 border-b-2 border-border pb-3 text-foreground tracking-tight text-left ${animClass}`} style={animStyle}>{parseBoldText(headerText)}</h3>;
      }
      
      // List items (robust: matches '-', '•', '*', '1. ', etc.)
      if (/^([-•*]|\d+\.)\s+/.test(trimmed)) {
          const cleanItem = trimmed.replace(/^([-•*]|\d+\.)\s+/, '');
          return (
            <div key={i} className={`flex gap-4 md:gap-5 mb-5 items-start pl-1 md:pl-2 text-left ${animClass}`} style={animStyle}>
              <span className="text-nyt-accent mt-1.5 flex-shrink-0"><CheckCircle2 size={16} strokeWidth={3} /></span>
              <span className="text-lg md:text-2xl text-foreground font-nyt-body leading-relaxed">{parseBoldText(cleanItem)}</span>
            </div>
          );
      }

      // First paragraph (Drop Cap style)
      if (i === 0) {
          return (
            <div key={i} className={`mb-8 md:mb-10 text-left ${animClass}`} style={animStyle}>
                <span className="editorial-byline">Od urednickiot tim na Presek</span>
                <p className="mb-6 md:mb-8 text-lg md:text-2xl leading-relaxed text-foreground font-serif italic border-l-4 border-nyt-accent pl-4 md:pl-6 py-2 bg-secondary/5 rounded-r-lg drop-cap">
                    {parseBoldText(trimmed)}
                </p>
            </div>
          );
      }

      // Regular paragraphs
      return <p key={i} className={`mb-4 md:mb-6 text-base md:text-xl leading-relaxed text-foreground/80 font-nyt-body text-left ${animClass}`} style={animStyle}>{parseBoldText(trimmed)}</p>;
    });
  };

  const modes = [
    { id: 'facts' as const, label: 'Fakti', icon: BarChart3, desc: 'Brojki i podatoci.' },
    { id: 'perspectives' as const, label: 'Perspektivi', icon: Users, desc: 'Izjavi i agli.' },
    { id: 'context' as const, label: 'kontekst', icon: BookOpen, desc: 'pozadina i posledice.' },
  ];
  const displayedSources = [...new Set<string>(Array.isArray(data?.sources) ? data.sources : sources)];

  return (
    <section className="research-analyst-container mt-8 mb-10 border border-border bg-secondary/5 p-4 md:p-6 relative overflow-hidden break-words">
      <div className="relative z-10 mb-6 flex flex-col gap-2">
        <div className="max-w-full md:max-w-3xl">
          <p className="mb-2 flex items-center gap-2 font-sans text-[9px] font-black uppercase tracking-[0.2em] text-nyt-accent">
            <div className="w-4 h-[2px] bg-nyt-accent"></div>
            PRESEK ISTRAZUVAC
          </p>
          <h2 className="font-serif text-xl md:text-2xl font-black text-foreground mb-2 leading-tight tracking-tight">Postavi prasanje ili pobaraj analiza</h2>
          <p className="font-serif text-sm md:text-base leading-relaxed text-secondary-foreground italic opacity-90">
            Izberete sto vi nedostiga: brojki, stavovi na akteri ili siri kontekst.
          </p>
        </div>
      </div>

      <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-4">
        {modes.map((m) => (
          <div
            key={m.id}
            className={`group relative p-5 text-left border border-border bg-background shadow-sm transition-all hover:shadow-md hover:border-nyt-accent/40 flex flex-col h-full ${loading && loading !== m.id ? 'opacity-60' : ''}`}
          >
            <div className={`w-10 h-10 flex items-center justify-center rounded-full mb-4 transition-all bg-secondary text-muted-foreground group-hover:bg-nyt-accent group-hover:text-white`}>
              {loading === m.id ? <Loader2 className="animate-spin" size={20} /> : <m.icon size={18} />}
            </div>
            
            <h4 className="font-black text-xs mb-1 uppercase tracking-[0.14em] text-foreground group-hover:text-nyt-accent transition-colors">{m.label}</h4>
            
            <p className="text-xs text-muted-foreground leading-snug font-medium mb-4 flex-grow">{m.desc}</p>
            
            <button
                onClick={() => performResearch(m.id)}
                disabled={!!loading}
                aria-busy={loading === m.id}
                className="w-full py-2 bg-secondary/50 group-hover:bg-nyt-accent group-hover:text-white transition-all text-[9px] font-black uppercase tracking-widest flex items-center justify-center gap-1 border border-border/50 group-hover:border-transparent disabled:cursor-wait disabled:opacity-70"
            >
                {loading === m.id ? 'Analizira...' : 'Istrazi'}
                {!loading && <ChevronRight size={10} />}
            </button>
          </div>
        ))}
      </div>

      {/* Custom Research Input */}
      <div className="relative z-10 mt-6 bg-background p-1.5 border border-border focus-within:border-nyt-accent/50 shadow-inner">
        <div className="flex flex-col md:flex-row gap-2">
            <div className="relative flex-grow">
                <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-muted-foreground opacity-50" size={22} />
                <input 
                    type="text" 
                    placeholder={placeholders[placeholderIdx]}
                    value={customQuery}
                    onChange={(e) => setCustomQuery(e.target.value)}
                    className="w-full pl-14 pr-4 py-5 bg-transparent outline-none font-serif italic text-xl transition-all duration-300"
                    onKeyDown={(e) => e.key === 'Enter' && customQuery.trim() && performResearch('custom', customQuery.trim())}
                />
            </div>
            <button 
                onClick={() => performResearch('custom', customQuery.trim())}
                disabled={!customQuery.trim() || !!loading}
                aria-busy={loading === 'custom'}
                className="w-full md:w-auto px-12 py-5 bg-foreground text-background font-black uppercase tracking-[0.2em] text-[11px] hover:bg-nyt-accent transition-all disabled:opacity-30 flex items-center justify-center gap-2"
            >
                {loading === 'custom' ? (
                    <><Loader2 className="animate-spin" size={18} /> Se analizira</>
                ) : (
                    <>Istrazi <ChevronRight size={14} /></>
                )}
            </button>
        </div>
      </div>

      {error && (
        <div className="mt-8 p-5 border-2 border-red-500/20 bg-red-500/5 text-red-600 dark:text-red-400 text-sm font-bold rounded-xl flex flex-col sm:flex-row sm:justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-3">
             <X size={18} className="flex-shrink-0" />
             <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="uppercase text-[10px] tracking-widest underline whitespace-nowrap">Zatvori</button>
        </div>
      )}

      {data && (
        <div ref={resultsRef} className="mt-8 editorial-panel p-0 overflow-hidden border border-nyt-accent/20 bg-background motion-rise w-full">
          <div className="border-b border-nyt-accent/20 bg-nyt-accent/8 px-4 md:px-6 py-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles size={16} className="text-nyt-accent" fill="currentColor" />
              <span className="text-[10px] md:text-[11px] font-black uppercase tracking-[0.18em] text-foreground">
                {data.mode === 'custom' ? 'odgovor na istrazuvanjeto' : modes.find(m => m.id === data.mode)?.label}
              </span>
            </div>

            <span className="text-[9px] font-black uppercase tracking-[0.18em] text-muted-foreground hidden sm:block">
              Presek Istrazuvac
            </span>

            <button onClick={() => setData(null)} className="p-1 hover:bg-foreground/5 rounded-lg transition-colors ml-auto">
                <X size={20} />
            </button>
          </div>
          
          <div className="p-4 md:p-8 relative">
             <div className="max-w-full md:max-w-3xl">
                {formatText(data.report)}

                {/* Follow-up Suggestions */}
                {data.mode === 'custom' && data.suggestions && data.suggestions.length > 0 && (
                  <div className="mt-12 pt-8 border-t border-border/40">
                    <p className="font-sans text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent mb-6 flex items-center gap-2">
                      <ChevronRight size={12} strokeWidth={3} /> sledece ISTRAZUVANjE
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

             </div>
             
             <div className="mt-8 pt-6 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 opacity-40">
                <div className="flex items-center gap-3 text-[9px] font-bold uppercase tracking-widest text-left">
                   <div className="w-2 h-2 rounded-full bg-nyt-accent animate-pulse flex-shrink-0"></div>
                   odgovor generiran od klasterskite izvori
                </div>
             </div>
          </div>
        </div>
      )}
    </section>
  );
}
