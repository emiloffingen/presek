import React, { useEffect, useRef, useState } from 'react';
import { navigate } from 'astro:transitions/client';
import { Search, X, Zap, ArrowUpRight, LoaderCircle } from 'lucide-react';
import { getDisplaySummary, getDisplayTitle } from '../utils/textUtils';

type Suggestion = {
  cluster_id: string;
  title: string;
  source?: string;
  category?: string;
  description?: string;
  sourceCount?: number;
  matchLabel?: string;
};

type TrendingItem = {
  word: string;
};

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export default function SearchIsland({ initialQuery = '' }: { initialQuery?: string | null }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(initialQuery || '');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [trendingItems, setTrendingItems] = useState<TrendingItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

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

  useEffect(() => {
    if (!isOpen) {
      document.body.style.overflow = 'unset';
      setActiveIndex(-1);
      setSuggestions([]);
      if (lastFocusedRef.current) {
        lastFocusedRef.current.focus();
      }
      return;
    }

    lastFocusedRef.current = document.activeElement as HTMLElement;
    document.body.style.overflow = 'hidden';
    
    // Use a small delay to ensure focus works on all browsers when opening
    const timer = setTimeout(() => {
      inputRef.current?.focus();
      if (query) {
        inputRef.current?.setSelectionRange(query.length, query.length);
      }
    }, 10);

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
      try {
        const res = await fetch(`/api/news?q=${encodeURIComponent(trimmed)}&page_size=6`);
        if (!res.ok) {
          throw new Error('search failed');
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
          setActiveIndex(-1); // Don't auto-select the first suggestion, let Enter perform general search
        }
      } catch {
        if (!cancelled) {
          setSuggestions([]);
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
  }, [query, isOpen]);

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
    navigate(`/?q=${encodeURIComponent(cleanQuery)}`);
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
    if (!cleanQuery) return text;

    const escapedQuery = cleanQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'ig');
    const parts = text.split(regex);

    return parts.map((part, index) => {
      if (part.toLowerCase() === cleanQuery.toLowerCase()) {
        return (
          <mark
            key={`${part}-${index}`}
            className="bg-transparent text-nyt-red underline decoration-nyt-red/70 underline-offset-4"
          >
            {part}
          </mark>
        );
      }
      return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
    });
  };

  const buildSnippet = (item: Suggestion, searchQuery: string) => {
    const description = item.description?.trim();
    if (!description) return '';

    const cleanQuery = searchQuery.trim().toLowerCase();
    if (!cleanQuery) return description.slice(0, 140);

    const matchIndex = description.toLowerCase().indexOf(cleanQuery);
    if (matchIndex === -1) return description.slice(0, 140);

    const start = Math.max(0, matchIndex - 42);
    const end = Math.min(description.length, matchIndex + cleanQuery.length + 84);
    const snippet = description.slice(start, end).trim();
    return `${start > 0 ? '…' : ''}${snippet}${end < description.length ? '…' : ''}`;
  };

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 text-foreground hover:text-muted-foreground transition-colors"
        aria-label="Пребарај"
      >
        <Search size={18} />
        <span className="text-[10px] font-black uppercase tracking-widest hidden sm:inline">Пребарај</span>
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
                  placeholder="Внесете клучни зборови..."
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

              <div className="mt-4 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.12em] text-nyt-accent">
                <Zap size={10} /> Пребарување низ консолидирани наративи во реално време
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

                    {!isLoading && suggestions.length === 0 && (
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
                          <button
                            type="button"
                            onClick={() => navigate('/archive')}
                            className="px-4 py-2 border border-border font-sans text-[10px] font-black uppercase tracking-[0.16em] text-foreground"
                          >
                            Архива
                          </button>
                        </div>
                      </div>
                    )}

                    {!isLoading &&
                      suggestions.map((item, index) => (
                        <button
                          key={item.cluster_id}
                          id={`search-suggestion-${item.cluster_id}`}
                          type="button"
                          role="option"
                          aria-selected={activeIndex === index}
                          onClick={() => navigateToCluster(item.cluster_id)}
                        className={`w-full text-left border-b border-border py-4 transition-colors ${
                          activeIndex === index
                              ? 'text-nyt-accent bg-secondary'
                              : 'text-foreground hover:text-nyt-accent'
                        }`}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-4 min-w-0">
                              <span className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground pt-1 shrink-0">
                                {String(index + 1).padStart(2, '0')}
                              </span>
                              <div className="min-w-0">
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
                                  {[item.source, item.sourceCount ? `${item.sourceCount} извори` : ''].filter(Boolean).join(' · ')}
                                </p>
                              </div>
                            </div>
                            <ArrowUpRight size={16} className="mt-1 shrink-0" />
                          </div>
                        </button>
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
                      <button
                        key={item}
                        onClick={() => navigateToQuery(item)}
                        className="w-full text-left font-serif font-black text-xl text-foreground hover:text-nyt-accent transition-colors"
                      >
                        {item}
                      </button>
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
                          <button
                            key={cat.name}
                            type="button"
                            onClick={() => { closeSearch(); navigate(`/?category=${encodeURIComponent(cat.name)}`); }}
                            className="flex items-center justify-between p-3 border border-border hover:border-nyt-accent hover:bg-secondary transition-all text-left group"
                          >
                            <span className={`font-serif font-bold ${cat.color}`}>{cat.name}</span>
                            <ArrowUpRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="px-5 md:px-8 py-6 md:py-0 md:pt-0 bg-[color:color-mix(in_srgb,var(--background)_90%,var(--secondary)_10%)]">
                <h3 className="font-sans text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground mb-5 pb-2 border-b border-border">
                  ПОПУЛАРНО ДЕНЕС
                </h3>
                <div className="space-y-3">
                  {(trendingItems.length > 0
                    ? trendingItems
                    : [
                        { word: 'Влада' },
                        { word: 'Економија' },
                        { word: 'Избори' },
                        { word: 'ЕУ' },
                        { word: 'Скопје' },
                        { word: 'Технологија' },
                      ]
                  ).map((item, index) => (
                    <button
                      key={item.word}
                      onClick={() => navigateToQuery(item.word)}
                      className="w-full flex items-center justify-between gap-3 border-b border-border py-3 text-left text-foreground hover:text-nyt-accent transition-colors"
                    >
                      <span className="flex items-center gap-3 min-w-0">
                        <span className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground shrink-0">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="font-serif font-bold text-lg text-balance">{item.word}</span>
                      </span>
                      <ArrowUpRight size={15} className="shrink-0" />
                    </button>
                  ))}
                </div>

                <div className="mt-8 pt-5 border-t border-border">
                  <p className="font-sans text-[10px] font-extrabold uppercase tracking-[0.16em] text-muted-foreground mb-3">
                    Брзи Патеки
                  </p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    <button
                      type="button"
                      onClick={() => { closeSearch(); navigate('/briefing'); }}
                      className="px-3 py-1.5 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground hover:border-nyt-accent hover:text-nyt-accent"
                    >
                      Брифинг
                    </button>
                    <button
                      type="button"
                      onClick={() => { closeSearch(); navigate('/archive'); }}
                      className="px-3 py-1.5 border border-border font-sans text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground hover:border-nyt-accent hover:text-nyt-accent"
                    >
                      Архива
                    </button>
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
