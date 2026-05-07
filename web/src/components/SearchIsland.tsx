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
          className="fixed inset-0 z-[1000] bg-[color:color-mix(in_srgb,var(--background)_84%,black_16%)]/96 backdrop-blur-md flex flex-col items-center pt-8 md:pt-12 px-4 transition-all animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="presek-search-title"
          onKeyDown={onDialogKeyDown}
          onClick={closeSearch}
        >
          <div
            ref={dialogRef}
            className="w-full max-w-4xl relative border border-[color:color-mix(in_srgb,var(--border)_88%,transparent)] bg-background shadow-[0_20px_80px_rgba(0,0,0,0.16)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center px-5 md:px-8 pt-5 md:pt-6 mb-8">
              <div className="flex items-center gap-3">
                <img src="/img/presek_emblem.svg?v=3" alt="ПРЕСЕК.мк" className="h-6 site-emblem" />
                <div>
                  <span id="presek-search-title" className="font-serif font-black text-lg block">
                    ИСТРАЖУВАЊЕ НА АРХИВАТА
                  </span>
                  <span className="font-sans text-[10px] font-extrabold uppercase tracking-[0.14em] text-muted-foreground">
                    Длабинско мапирање на теми и настани
                  </span>
                </div>
              </div>
              <button
                onClick={closeSearch}
                className="p-2 text-foreground hover:bg-secondary transition-colors"
                aria-label="Затвори пребарување"
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={onSubmit} className="mb-8 px-5 md:px-8">
              <div className="border-y border-foreground/70 flex items-center gap-2 py-1 relative">
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={placeholders[placeholderIdx]}
                  className="w-full bg-transparent py-3 text-2xl md:text-4xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground min-w-0"
                  aria-label="Пребарај вести"
                  role="combobox"
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck="false"
                  aria-autocomplete="list"
                  aria-controls={showSuggestions && suggestions.length > 0 ? 'presek-search-listbox' : undefined}
                  aria-expanded={showSuggestions && suggestions.length > 0}
                  aria-activedescendant={
                    activeIndex >= 0 && suggestions[activeIndex]
                      ? `search-suggestion-${suggestions[activeIndex].cluster_id}`
                      : undefined
                  }
                />
                <div className="flex items-center gap-1 shrink-0">
                  {query && (
                    <button
                      type="button"
                      onClick={() => { setQuery(''); inputRef.current?.focus(); }}
                      className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                      aria-label="Исчисти пребарување"
                    >
                      <X size={24} />
                    </button>
                  )}
                  <button
                    type="submit"
                    className="bg-foreground text-background px-4 md:px-8 py-3 font-black text-[11px] uppercase tracking-[0.18em] hover:opacity-85 transition-all"
                  >
                    Барај
                  </button>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.12em] text-nyt-accent">
                    <Zap size={10} /> Пребарување низ консолидирани наративи во реално време
                </div>

                <div className="flex items-center gap-1.5 p-1 bg-secondary/50 rounded-sm border border-border">
                   {[
                     { id: '24h', label: '24 ЧАСА' },
                     { id: '7d', label: '7 ДЕНА' },
                     { id: '30d', label: '30 ДЕНА' },
                     { id: 'all', label: 'СИТЕ' }
                   ].map(ts => (
                     <button
                        key={ts.id}
                        type="button"
                        onClick={() => setTimespan(ts.id)}
                        className={`px-3 py-1 font-sans text-[9px] font-black tracking-widest transition-all ${
                            timespan === ts.id 
                            ? 'bg-foreground text-background shadow-sm' 
                            : 'text-muted-foreground hover:text-foreground'
                        }`}
                     >
                       {ts.label}
                     </button>
                   ))}
                </div>
              </div>
            </form>

            <div id="presek-search-results" className="grid grid-cols-1 md:grid-cols-[minmax(0,1.3fr)_minmax(18rem,0.8fr)] gap-0">
              <div className="px-5 md:px-8 pb-6 md:pb-8 md:border-r border-border">
                <h3 className="font-sans text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground mb-5 pb-2 border-b border-border">
                  {showSuggestions ? 'РЕЗУЛТАТИ' : 'ПОСЛЕДНИ ПРЕБАРУВАЊА'}
                </h3>

                {showSuggestions && (
                  <div
                    id="presek-search-listbox"
                    role="listbox"
                    aria-label="Резултати од пребарување"
                    className="space-y-2"
                  >
                    {isLoading && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                        <LoaderCircle size={16} className="animate-spin" />
                        <span>Пребарувам релевантни вести...</span>
                      </div>
                    )}

                    {error && (
                      <div className="p-4 border border-nyt-red/20 bg-nyt-red/5 text-nyt-red text-sm flex items-center gap-3">
                        <Zap size={14} />
                        <span>{error}</span>
                      </div>
                    )}

                    {entityResult && (
                      <a
                        href={`/?entity=${encodeURIComponent(entityResult.name)}`}
                        onClick={(e) => { e.preventDefault(); closeSearch(); navigate(`/?entity=${encodeURIComponent(entityResult.name)}`); }}
                        className="w-full mb-6 p-5 border-2 border-nyt-accent/20 bg-nyt-accent/[0.03] hover:bg-nyt-accent/[0.06] transition-colors flex items-center gap-6 group text-left no-underline"
                      >
                        <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center shrink-0 border border-border overflow-hidden">
                           {entityResult.image_url ? (
                             <img src={`/proxy?url=${encodeURIComponent(entityResult.image_url)}&w=128`} alt="" className="w-full h-full object-cover" />
                           ) : (
                             <span className="font-serif font-black text-2xl text-muted-foreground">{entityResult.name[0]}</span>
                           )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="font-sans text-[9px] font-black uppercase tracking-[0.14em] text-nyt-accent mb-1 block">Профил на субјект</span>
                          <h4 className="font-serif font-black text-2xl mb-1 group-hover:underline decoration-nyt-accent decoration-2 underline-offset-4">{entityResult.name}</h4>
                          <p className="font-sans text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                            {entityResult.total_mentions.toLocaleString('mk-MK')} споменувања · {entityResult.sentiment_score > 0.1 ? 'Позитивен' : entityResult.sentiment_score < -0.1 ? 'Негативен' : 'Неутрален'} тон
                          </p>
                        </div>
                        <ArrowUpRight size={20} className="text-muted-foreground group-hover:text-nyt-accent transition-colors" />
                      </a>
                    )}

                    {!isLoading && !error && suggestions.length === 0 && !entityResult && (
                      <div className="space-y-4">
                        <p className="font-nyt-body text-base text-secondary-foreground leading-relaxed">
                          Нема директни совпаѓања. Притиснете <strong>Барај</strong> за да ја отворите страницата со резултати.
                        </p>
                        <div className="flex flex-wrap gap-3">
                          <button
                            type="button"
                            onClick={() => navigateToQuery(query)}
                            className="px-4 py-2 bg-foreground text-background font-sans text-[10px] font-black uppercase tracking-[0.16em]"
                          >
                            Отвори ги сите резултати
                          </button>
                          <a
                            href="/archive"
                            onClick={(e) => { e.preventDefault(); closeSearch(); navigate('/archive'); }}
                            className="px-4 py-2 border border-border font-sans text-[10px] font-black uppercase tracking-[0.16em] text-foreground"
                          >
                            Архива
                          </a>
                        </div>
                      </div>
                    )}

                    {!isLoading &&
                      suggestions.map((item, index) => (
                        <a
                          key={item.cluster_id}
                          id={`search-suggestion-${item.cluster_id}`}
                          href={`/cluster/${item.cluster_id}`}
                          role="option"
                          aria-selected={activeIndex === index}
                          onClick={(e) => { e.preventDefault(); navigateToCluster(item.cluster_id); }}
                          className={`w-full text-left border-b border-border py-4 transition-colors block no-underline ${
                            activeIndex === index
                                ? 'text-nyt-accent bg-secondary'
                                : 'text-foreground hover:text-nyt-accent'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-4 min-w-0 flex-1">
                              <span className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground pt-1 shrink-0">
                                {String(index + 1).padStart(2, '0')}
                              </span>
                              
                              <div className="min-w-0 flex-1">
                                <div className="mb-2 flex flex-wrap items-center gap-2">
                                  {item.matchLabel && (
                                    <span className="border border-border px-2 py-0.5 font-sans text-[9px] font-black uppercase tracking-[0.12em] text-muted-foreground">
                                      {item.matchLabel}
                                    </span>
                                  )}
                                  {item.category && (
                                    <span className="font-sans text-[9px] font-black uppercase tracking-[0.12em] text-nyt-accent">
                                      {item.category}
                                    </span>
                                  )}
                                </div>
                                <p className="font-serif font-black text-xl leading-tight mb-2 text-balance">
                                  {renderHighlightedText(item.title, query)}
                                </p>
                                {item.description && (
                                  <p className="mb-3 font-nyt-body text-sm leading-6 text-secondary-foreground">
                                    {renderHighlightedText(buildSnippet(item, query), query)}
                                  </p>
                                )}
                                <p className="font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-muted-foreground">
                                  Кластер
                                  {item.source || item.sourceCount ? ' · ' : ''}
                                  {[item.source, item.sourceCount ? `${item.sourceCount} ${item.sourceCount === 1 ? 'извор' : 'извори'}` : ''].filter(Boolean).join(' · ')}

                                </p>
                              </div>

                              {item.image_url && (
                                <div className="hidden sm:block shrink-0 w-24 aspect-[4/3] overflow-hidden border border-border bg-secondary/20">
                                    <img 
                                        src={`/proxy?url=${encodeURIComponent(item.image_url)}&w=200`} 
                                        alt="" 
                                        className="w-full h-full object-cover"
                                        loading="lazy"
                                    />
                                </div>
                              )}
                            </div>
                            <ArrowUpRight size={16} className="mt-1 shrink-0" />
                          </div>
                        </a>
                      ))}
                  </div>
                )}

                {showRecent && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-4">
                      <p className="font-sans text-[10px] font-black uppercase tracking-[0.14em] text-muted-foreground">
                        Последни пребарувања
                      </p>
                      <button
                        type="button"
                        onClick={clearRecentSearches}
                        className="font-sans text-[10px] font-black uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
                      >
                        Исчисти
                      </button>
                    </div>
                    {recentSearches.map((item) => (
                      <a
                        key={item}
                        href={`/?q=${encodeURIComponent(item)}`}
                        onClick={(e) => { e.preventDefault(); navigateToQuery(item); }}
                        className="w-full text-left font-serif font-black text-xl text-foreground hover:text-nyt-accent transition-colors block no-underline mb-2"
                      >
                        {item}
                      </a>
                    ))}
                  </div>
                )}

                {!showSuggestions && !showRecent && (
                  <div className="space-y-6">
                    <p className="font-nyt-body text-base text-secondary-foreground leading-relaxed max-w-[42ch]">
                      Почнете со име на личност, институција, град или тема за да добиете релевантни групирани вести.
                    </p>
                    <div className="pt-4">
                      <p className="font-sans text-[10px] font-black uppercase tracking-[0.14em] text-muted-foreground mb-4">
                        Истражи по категорија
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        {SUGGESTED_CATEGORIES.map(cat => (
                          <a
                            key={cat.name}
                            href={`/?category=${encodeURIComponent(cat.name)}`}
                            onClick={(e) => { e.preventDefault(); closeSearch(); navigate(`/?category=${encodeURIComponent(cat.name)}`); }}
                            className="flex items-center justify-between p-3 border border-border hover:border-nyt-accent hover:bg-secondary transition-all text-left group no-underline"
                          >
                            <span className={`font-serif font-bold ${cat.color}`}>{cat.name}</span>
                            <ArrowUpRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="px-5 md:px-8 py-6 md:py-0 md:pt-0 bg-[color:color-mix(in_srgb,var(--background)_90%,var(--secondary)_10%)]">
                <h3 className="font-sans text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground mb-5 pb-2 border-b border-border">
                  ТРЕНД ПРЕБАРУВАЊА
                </h3>
                <div className="space-y-3">
                  {(trendingItems.length > 0
                    ? trendingItems
                    : [
                        { word: 'СДСМ' },
                        { word: 'Влада' },
                        { word: 'ЕУ' },
                        { word: 'Доналд Трамп' },
                        { word: 'Венко Филипче' },
                        { word: 'Скопје' },
                      ]
                  ).map((item, index) => (
                    <a
                      key={item.word}
                      href={`/?q=${encodeURIComponent(item.word)}`}
                      onClick={(e) => { e.preventDefault(); navigateToQuery(item.word); }}
                      className="w-full flex items-center justify-between gap-3 border-b border-border py-3 text-left text-foreground hover:text-nyt-accent transition-colors no-underline"
                    >
                      <span className="flex items-center gap-3 min-w-0">
                        <span className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground shrink-0">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="font-serif font-bold text-lg text-balance">{item.word}</span>
                      </span>
                      <ArrowUpRight size={15} className="shrink-0" />
                    </a>
                  ))}
                </div>

                <div className="mt-8 pt-5 border-t border-border">
                  <p className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground mb-3">
                    Брзи Патеки
                  </p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    <a
                      href="/briefing"
                      onClick={(e) => { e.preventDefault(); closeSearch(); navigate('/briefing'); }}
                      className="px-3 py-1.5 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground hover:border-nyt-accent hover:text-nyt-accent"
                    >
                      Брифинг
                    </a>
                    <a
                      href="/archive"
                      onClick={(e) => { e.preventDefault(); closeSearch(); navigate('/archive'); }}
                      className="px-3 py-1.5 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground hover:border-nyt-accent hover:text-nyt-accent"
                    >
                      Архива
                    </a>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="px-2.5 py-1 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-muted-foreground">
                      Ctrl/Cmd + K
                    </span>
                    <span className="px-2.5 py-1 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-muted-foreground">
                      ↑ ↓ избор
                    </span>
                    <span className="px-2.5 py-1 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-muted-foreground">
                      Enter отвори
                    </span>
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
