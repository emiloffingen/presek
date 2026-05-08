import React, { useEffect, useRef, useState } from 'react';
import { navigate } from 'astro:transitions/client';
import { Search, X, Zap, ArrowUpRight, LoaderCircle } from 'lucide-react';
import { getDisplaySummary, getDisplayTitle } from '../utils/textUtils';

type Suggestion = {
  cluster_id: string;
  title: string;
  image_url?: string | null;
  source?: string;
  category?: string;
  description?: string;
  sourceCount?: number;
  matchLabel?: string;
};

type EntityResult = {
  name: string;
  type: string;
  total_mentions: number;
  sentiment_score: number;
  image_url?: string | null;
};

type TrendingItem = {
  word: string;
};

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export default function SearchIsland({ initialQuery = '' }: { initialQuery?: string | null }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(initialQuery || '');
  const [timespan, setTimespan] = useState('all');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [entityResult, setEntityResult] = useState<EntityResult | null>(null);
  const [trendingItems, setTrendingItems] = useState<TrendingItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const placeholders = [
    "Пребарувај низ архивата...",
    "Кој е главниот конфликт?",
    "Што велат бројките?",
    "Какви се реакциите?",
    "Што се случува во Скопје?"
  ];

  useEffect(() => {
    const interval = setInterval(() => {
        setPlaceholderIdx((prev) => (prev + 1) % placeholders.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (initialQuery !== undefined && initialQuery !== null && query !== initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  useEffect(() => {
    const saved = localStorage.getItem('presek_recent_searches');
    if (saved) {
      try {
        setRecentSearches(JSON.parse(saved));
      } catch {
        setRecentSearches([]);
      }
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') setIsOpen(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      document.body.style.overflow = 'unset';
      setActiveIndex(-1);
      setSuggestions([]);
      setError(null);
      if (lastFocusedRef.current) {
        lastFocusedRef.current.focus();
      }
      return;
    }

    lastFocusedRef.current = document.activeElement as HTMLElement;
    document.body.style.overflow = 'hidden';
    
    // Improved focus for all devices
    const timer = setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        // Force focus for iOS
        inputRef.current.click();
      }
    }, 50);

    return () => {
      document.body.style.overflow = 'unset';
      clearTimeout(timer);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;

    const loadTrending = async () => {
      try {
        const res = await fetch('/api/trending');
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data)) {
          setTrendingItems(data.slice(0, 6));
        }
      } catch {
        if (!cancelled) {
          setTrendingItems([]);
        }
      }
    };

    loadTrending();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setIsLoading(false);
      setActiveIndex(-1);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const url = `/api/news?q=${encodeURIComponent(trimmed)}&page_size=6`;
        const timespanPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
        const res = await fetch(url + timespanPart);
        if (!res.ok) {
          throw new Error('Системот е привремено зафатен. Ве молиме обидете се повторно.');
        }
        const data = await res.json();
        const nextSuggestions = Array.isArray(data?.clusters)
          ? data.clusters.slice(0, 6).map((cluster: any) => {
              const article = cluster.articles?.[0] || {};
              const title = getDisplayTitle(article, 'Наслов') || 'Наслов';
              const lowered = title.toLowerCase();
              const queryLower = trimmed.toLowerCase();
              return {
                cluster_id: cluster.cluster_id,
                title,
                image_url: article.image_url || null,
                source: article.source || '',
                category: article.category || '',
                description: getDisplaySummary(article),
                sourceCount: Array.isArray(cluster.articles) ? cluster.articles.length : 0,
                matchLabel:
                  lowered === queryLower
                    ? 'Точен наслов'
                    : lowered.includes(queryLower)
                    ? 'Совпаѓање во наслов'
                    : 'Поврзана тема',
              };
            })
          : [];

        if (!cancelled) {
          setSuggestions(nextSuggestions);
          setEntityResult(data.entity || null);
          setActiveIndex(-1);
        }
      } catch (err) {
        if (!cancelled) {
          setSuggestions([]);
          setEntityResult(null);
          setError(err instanceof Error ? err.message : 'Грешка при пребарувањето');
          setActiveIndex(-1);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, isOpen, timespan]);

  const closeSearch = () => {
    setIsOpen(false);
  };

  const persistRecentSearch = (searchQuery: string) => {
    const cleanQuery = searchQuery.trim();
    if (!cleanQuery) return;

    const newRecent = [cleanQuery, ...recentSearches.filter((s) => s !== cleanQuery)].slice(0, 5);
    setRecentSearches(newRecent);
    localStorage.setItem('presek_recent_searches', JSON.stringify(newRecent));
  };

  const navigateToQuery = (searchQuery: string) => {
    const cleanQuery = searchQuery.trim();
    if (!cleanQuery) return;
    persistRecentSearch(cleanQuery);
    closeSearch();
    const tsPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
    navigate(`/?q=${encodeURIComponent(cleanQuery)}${tsPart}`);
  };

  const navigateToCluster = (clusterId: string) => {
    if (!clusterId) return;
    closeSearch();
    navigate(`/cluster/${clusterId}`);
  };

  const clearRecentSearches = () => {
    setRecentSearches([]);
    localStorage.removeItem('presek_recent_searches');
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (activeIndex >= 0 && suggestions[activeIndex]) {
      navigateToCluster(suggestions[activeIndex].cluster_id);
      return;
    }
    navigateToQuery(query);
  };

  const onDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown') {
      if (suggestions.length === 0) return;
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
      return;
    }

    if (e.key === 'ArrowUp') {
      if (suggestions.length === 0) return;
      e.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
      return;
    }

    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((node) => !node.hasAttribute('disabled'));

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  const showRecent = query.trim().length < 2 && recentSearches.length > 0;
  const showSuggestions = query.trim().length >= 2;

  const SUGGESTED_CATEGORIES = [
    { name: 'Економија', color: 'text-emerald-600' },
    { name: 'Политика', color: 'text-blue-600' },
    { name: 'Спорт', color: 'text-orange-500' },
    { name: 'Култура', color: 'text-purple-600' },
    { name: 'Технологија', color: 'text-cyan-600' },
    { name: 'Македонија', color: 'text-nyt-red' },
  ];

  const renderHighlightedText = (text: string, searchQuery: string) => {
    const cleanQuery = searchQuery.trim();
    if (!cleanQuery || cleanQuery.length < 2) return text;

    try {
      // Escape for regex but handle Cyrillic safely
      const escapedQuery = cleanQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escapedQuery})`, 'ig');
      const parts = text.split(regex);

      return parts.map((part, index) => {
        if (part.toLowerCase() === cleanQuery.toLowerCase()) {
          return (
            <mark
              key={`${part}-${index}`}
              className="bg-nyt-accent/10 text-nyt-accent px-0.5 rounded-sm"
            >
              {part}
            </mark>
          );
        }
        return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
      });
    } catch {
      return text;
    }
  };

  const buildSnippet = (item: Suggestion, searchQuery: string) => {
    const description = item.description?.trim() || "";
    const cleanQuery = searchQuery.trim().toLowerCase();
    
    if (!cleanQuery || cleanQuery.length < 2) {
      return description.slice(0, 120);
    }

    const matchIndex = description.toLowerCase().indexOf(cleanQuery);
    if (matchIndex === -1) {
      return description.slice(0, 120);
    }

    const start = Math.max(0, matchIndex - 50);
    const end = Math.min(description.length, matchIndex + cleanQuery.length + 80);
    
    let snippet = description.slice(start, end).trim();
    if (start > 0) snippet = "…" + snippet;
    if (end < description.length) snippet = snippet + "…";
    
    return snippet;
  };

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 text-foreground hover:text-muted-foreground transition-colors group"
        aria-label="Пребарај"
      >
        <Search size={18} />
        <span className="text-[10px] font-black uppercase tracking-widest hidden sm:inline relative overflow-hidden h-4">
            <span key={placeholderIdx} className="animate-in slide-in-from-bottom-2 duration-300 block">
                {placeholders[placeholderIdx]}
            </span>
        </span>
      </button>

      {isOpen && (
        <div
          className="fixed inset-0 z-[1000] bg-background/60 backdrop-blur-xl flex flex-col items-center pt-4 md:pt-12 px-4 transition-all animate-in fade-in duration-300"
          role="dialog"
          aria-modal="true"
          aria-labelledby="presek-search-title"
          onKeyDown={onDialogKeyDown}
          onClick={closeSearch}
        >
          <div
            ref={dialogRef}
            className="w-full max-w-5xl relative border border-nyt-accent/10 bg-background/95 shadow-editorial rounded-lg overflow-hidden animate-in zoom-in-95 duration-300"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center px-6 md:px-10 py-6 border-b border-border/40">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-nyt-accent/10 rounded-lg">
                    <Search size={20} className="text-nyt-accent" />
                </div>
                <div>
                  <span id="presek-search-title" className="font-serif font-black text-xl md:text-2xl block tracking-tight">
                    ИСТРАЖУВАЊЕ НА АРХИВАТА
                  </span>
                  <span className="font-sans text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground opacity-70">
                    Длабинско мапирање на теми и настани
                  </span>
                </div>
              </div>
              <button
                onClick={closeSearch}
                className="p-2.5 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-full transition-all"
                aria-label="Затвори пребарување"
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={onSubmit} className="px-6 md:px-10 py-8 bg-secondary/20">
              <div className="relative group">
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={placeholders[placeholderIdx]}
                  className="w-full bg-transparent py-4 text-3xl md:text-5xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 min-w-0 transition-all"
                  aria-label="Пребарај вести"
                  role="combobox"
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck="false"
                />
                <div className="absolute bottom-0 left-0 w-full h-0.5 bg-border group-focus-within:bg-nyt-accent transition-colors"></div>
                
                <div className="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-3">
                  {query && (
                    <button
                      type="button"
                      onClick={() => { setQuery(''); inputRef.current?.focus(); }}
                      className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <X size={28} />
                    </button>
                  )}
                  <button
                    type="submit"
                    className="bg-nyt-accent text-white px-6 md:px-10 py-3.5 rounded font-black text-xs uppercase tracking-[0.2em] shadow-lg shadow-nyt-accent/20 hover:scale-[1.02] active:scale-95 transition-all"
                  >
                    БАРAJ
                  </button>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-2.5 text-[10px] font-black uppercase tracking-[0.15em] text-nyt-accent bg-nyt-accent/5 px-3 py-1.5 rounded-full border border-nyt-accent/10">
                    <Zap size={12} fill="currentColor" /> КОНСОЛИДИРАНИ НАРАТИВИ ВО РЕАЛНО ВРЕМЕ
                </div>

                <div className="flex items-center gap-1.5 p-1 bg-background/80 backdrop-blur-sm rounded-lg border border-border shadow-sm">
                   {[
                     { id: '24h', label: '24 ЧАСА' },
                     { id: '7d', label: '7 ДЕНА' },
                     { id: 'all', label: 'АРХИВА' }
                   ].map(ts => (
                     <button
                        key={ts.id}
                        type="button"
                        onClick={() => setTimespan(ts.id)}
                        className={`px-4 py-2 rounded-md font-sans text-[10px] font-black tracking-widest transition-all ${
                            timespan === ts.id 
                            ? 'bg-nyt-accent text-white shadow-md' 
                            : 'text-muted-foreground hover:text-foreground'
                        }`}
                     >
                       {ts.label}
                     </button>
                   ))}
                </div>
              </div>
            </form>

            <div id="presek-search-results" className="grid grid-cols-1 md:grid-cols-[1fr_320px] min-h-[400px]">
              <div className="px-6 md:px-10 py-8 md:border-r border-border/40 overflow-y-auto max-h-[60vh] hide-scrollbar">
                <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-8 flex items-center gap-3">
                  <span className="w-8 h-px bg-border"></span>
                  {showSuggestions ? 'РЕЗУЛТАТИ' : 'ПОСЛЕДНИ ПРЕБАРУВАЊА'}
                </h3>

                {showSuggestions && (
                  <div id="presek-search-listbox" role="listbox" className="space-y-4">
                    {isLoading && (
                      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground animate-pulse">
                        <LoaderCircle size={32} className="animate-spin mb-4 text-nyt-accent" />
                        <span className="font-sans text-xs font-black uppercase tracking-widest">Пребарувам релевантни вести...</span>
                      </div>
                    )}

                    {error && (
                      <div className="p-6 border border-nyt-red/20 bg-nyt-red/5 text-nyt-red rounded-lg flex items-center gap-4">
                        <Zap size={20} />
                        <span className="font-bold">{error}</span>
                      </div>
                    )}

                    {entityResult && (
                      <a
                        href={`/?entity=${encodeURIComponent(entityResult.name)}`}
                        onClick={(e) => { e.preventDefault(); closeSearch(); navigate(`/?entity=${encodeURIComponent(entityResult.name)}`); }}
                        className="w-full mb-8 p-6 border border-nyt-accent/20 bg-nyt-accent/[0.04] hover:bg-nyt-accent/[0.08] rounded-xl transition-all flex items-center gap-8 group no-underline shadow-sm hover:shadow-md"
                      >
                        <div className="w-20 h-20 rounded-full bg-background flex items-center justify-center shrink-0 border-2 border-nyt-accent/20 overflow-hidden shadow-inner">
                           {entityResult.image_url ? (
                             <img src={`/proxy?url=${encodeURIComponent(entityResult.image_url)}&w=128`} alt="" className="w-full h-full object-cover transition-transform group-hover:scale-110" />
                           ) : (
                             <span className="font-serif font-black text-3xl text-nyt-accent">{entityResult.name[0]}</span>
                           )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="font-sans text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent mb-2 block">ПРОФИЛ НА СУБЈЕКТ</span>
                          <h4 className="font-serif font-black text-3xl mb-1.5 group-hover:text-nyt-accent transition-colors">{entityResult.name}</h4>
                          <p className="font-sans text-xs font-bold text-muted-foreground uppercase tracking-widest">
                            {entityResult.total_mentions.toLocaleString('mk-MK')} СПОМЕНУВАЊА · {entityResult.sentiment_score > 0.1 ? 'ПОЗИТИВЕН' : entityResult.sentiment_score < -0.1 ? 'НЕГАТИВЕН' : 'НЕУТРАЛЕН'} ТОН
                          </p>
                        </div>
                        <div className="p-3 bg-background rounded-full border border-border group-hover:bg-nyt-accent group-hover:text-white transition-all">
                            <ArrowUpRight size={24} />
                        </div>
                      </a>
                    )}

                    {!isLoading && suggestions.map((item, index) => (
                        <a
                          key={item.cluster_id}
                          id={`search-suggestion-${item.cluster_id}`}
                          href={`/cluster/${item.cluster_id}`}
                          role="option"
                          aria-selected={activeIndex === index}
                          onClick={(e) => { e.preventDefault(); navigateToCluster(item.cluster_id); }}
                          className={`w-full text-left p-4 rounded-xl transition-all block no-underline border-b border-border/40 last:border-0 ${
                            activeIndex === index
                                ? 'bg-nyt-accent/5 border-nyt-accent/20 shadow-sm translate-x-1'
                                : 'hover:bg-secondary/40'
                          }`}
                        >
                          <div className="flex items-start gap-6">
                            <div className="min-w-0 flex-1">
                                <div className="mb-3 flex flex-wrap items-center gap-3">
                                  {item.matchLabel && (
                                    <span className="bg-secondary px-2.5 py-1 rounded text-[10px] font-black uppercase tracking-wider text-muted-foreground border border-border/50">
                                      {item.matchLabel}
                                    </span>
                                  )}
                                  {item.category && (
                                    <span className="text-[10px] font-black uppercase tracking-widest text-nyt-accent">
                                      {item.category}
                                    </span>
                                  )}
                                </div>
                                <p className="font-serif font-black text-2xl leading-tight mb-3 text-foreground group-hover:text-nyt-accent transition-colors">
                                  {renderHighlightedText(item.title, query)}
                                </p>
                                {item.description && (
                                  <p className="mb-4 font-nyt-body text-base leading-relaxed text-muted-foreground line-clamp-2">
                                    {renderHighlightedText(buildSnippet(item, query), query)}
                                  </p>
                                )}
                                <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">
                                  <span className="flex items-center gap-1.5"><Newspaper size={12} /> {item.source}</span>
                                  <span className="w-1 h-1 rounded-full bg-border"></span>
                                  <span>{item.sourceCount} {item.sourceCount === 1 ? 'ИЗВОР' : 'ИЗВОРИ'}</span>
                                </div>
                            </div>

                            {item.image_url && (
                                <div className="hidden sm:block shrink-0 w-32 aspect-[4/3] overflow-hidden rounded-lg border border-border shadow-sm">
                                    <img 
                                        src={`/proxy?url=${encodeURIComponent(item.image_url)}&w=200`} 
                                        alt="" 
                                        className="w-full h-full object-cover transition-transform group-hover:scale-105"
                                        loading="lazy"
                                    />
                                </div>
                            )}
                          </div>
                        </a>
                      ))}
                  </div>
                )}

                {showRecent && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {recentSearches.map((item) => (
                      <a
                        key={item}
                        href={`/?q=${encodeURIComponent(item)}`}
                        onClick={(e) => { e.preventDefault(); navigateToQuery(item); }}
                        className="flex items-center justify-between p-5 bg-secondary/30 hover:bg-secondary/60 rounded-xl border border-border/50 transition-all group no-underline"
                      >
                        <span className="font-serif font-black text-xl text-foreground group-hover:text-nyt-accent transition-colors">
                            {item}
                        </span>
                        <ArrowUpRight size={18} className="text-muted-foreground group-hover:text-nyt-accent" />
                      </a>
                    ))}
                  </div>
                )}
              </div>

              <div className="px-6 md:px-10 py-8 bg-secondary/10 flex flex-col">
                <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-8 flex items-center gap-3">
                  <span className="w-8 h-px bg-border"></span>
                  ТРЕНД ПРЕБАРУВАЊА
                </h3>
                <div className="space-y-4 flex-1">
                  {(trendingItems.length > 0 ? trendingItems : [
                    { word: 'СДСМ' }, { word: 'Влада' }, { word: 'ЕУ' }, 
                    { word: 'Доналд Трамп' }, { word: 'Венко Филипче' }, { word: 'Скопје' }
                  ]).map((item, index) => (
                    <a
                      key={item.word}
                      href={`/?q=${encodeURIComponent(item.word)}`}
                      onClick={(e) => { e.preventDefault(); navigateToQuery(item.word); }}
                      className="group flex items-center justify-between gap-4 p-3 rounded-lg hover:bg-white dark:hover:bg-zinc-900 transition-all no-underline"
                    >
                      <span className="flex items-center gap-4 min-w-0">
                        <span className="font-sans text-[10px] font-black text-nyt-accent/40 group-hover:text-nyt-accent shrink-0">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="font-serif font-black text-lg text-foreground group-hover:text-nyt-accent truncate">{item.word}</span>
                      </span>
                      <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-nyt-accent group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
                    </a>
                  ))}
                </div>

                <div className="mt-12 pt-8 border-t border-border/40">
                  <div className="grid grid-cols-2 gap-3 mb-8">
                    <a
                      href="/briefing"
                      onClick={(e) => { e.preventDefault(); closeSearch(); navigate('/briefing'); }}
                      className="flex items-center justify-center gap-2 p-3 bg-background border border-border rounded-lg font-sans text-[10px] font-black uppercase tracking-widest hover:border-nyt-accent hover:text-nyt-accent transition-all"
                    >
                      БРИФИНГ <ArrowUpRight size={12} />
                    </a>
                    <a
                      href="/archive"
                      onClick={(e) => { e.preventDefault(); closeSearch(); navigate('/archive'); }}
                      className="flex items-center justify-center gap-2 p-3 bg-background border border-border rounded-lg font-sans text-[10px] font-black uppercase tracking-widest hover:border-nyt-accent hover:text-nyt-accent transition-all"
                    >
                      АРХИВА <ArrowUpRight size={12} />
                    </a>
                  </div>
                  
                  <div className="flex flex-wrap gap-2 opacity-50">
                    <kbd className="px-2 py-1 bg-background border border-border rounded text-[9px] font-black uppercase">⌘ K</kbd>
                    <kbd className="px-2 py-1 bg-background border border-border rounded text-[9px] font-black uppercase">↑ ↓</kbd>
                    <kbd className="px-2 py-1 bg-background border border-border rounded text-[9px] font-black uppercase">ESC</kbd>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
