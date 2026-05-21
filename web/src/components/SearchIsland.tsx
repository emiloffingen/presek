import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { navigate } from 'astro:transitions/client';
import {
  Search, X, Zap, ArrowUpRight, LoaderCircle, Newspaper,
  Mic, Clock, TrendingUp, User, Layout,
  HelpCircle, Archive, Sparkles, ChevronRight,
  Globe, ShieldCheck, Activity, BookOpen, ExternalLink,
  History, Compass, SlidersHorizontal
} from 'lucide-react';
import { getDisplaySummary, getDisplayTitle } from '../utils/textUtils';

// Helper function to highlight matching search query text
function highlightMatch(text: string, query: string) {
  if (!query.trim()) return text;
  const escapedQuery = query.trim().replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
  const regex = new RegExp(`(${escapedQuery})`, 'gi');
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark key={i} className="bg-amber-500/20 text-amber-900 dark:bg-amber-500/30 dark:text-amber-300 font-bold px-0.5 rounded">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
}

type Suggestion = {
  cluster_id: string;
  title: string;
  image_url?: string | null;
  source?: string;
  category?: string;
  description?: string;
  sourceCount?: number;
  matchLabel?: string;
  created_at?: string;
  representative_image?: string;
  pulse_score?: number;
  has_synthesis?: boolean;
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

type SearchAction = {
  id: string;
  label: string;
  icon: any;
  href: string;
  category: 'NAVIGATION' | 'SETTINGS' | 'HELP';
  desc: string;
};

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export default function SearchIsland({ initialQuery = '', lang = 'sr' }: { initialQuery?: string | null, lang?: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(initialQuery || '');
  const [timespan, setTimespan] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [recentSearches, setRecentSearches] = useState<{query: string; timestamp: number}[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [entityResult, setEntityResult] = useState<EntityResult | null>(null);
  const [trendingItems, setTrendingItems] = useState<TrendingItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isListening, setIsListening] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [activeSection, setActiveSection] = useState<'NEWS' | 'ENTITIES' | 'ACTIONS' | 'RECENT'>('NEWS');

  const recognitionRef = useRef<any>(null);

  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const placeholders = lang === 'sr' ? [
    "Istraži medijsku arhivu...",
    "Analiziraj protivurečne stavove...",
    "Dekonstruiši činjenice i brojke...",
    "Mapiraj reakcije i posledice...",
    "Šta se dešava u Srbiji?"
  ] : [
    "Истражи ја медиумската архива...",
    "Анализирај противречни ставови...",
    "Деконструирај ги фактите и бројките...",
    "Мапирај реакции и последици...",
    "Што се случува во Македонија?"
  ];

  const SEARCH_ACTIONS: SearchAction[] = [
    { id: 'act-home', label: lang === 'sr' ? 'Početna Stranica' : 'Почетна Страница', icon: Layout, href: lang === 'sr' ? '/' : '/mk', category: 'NAVIGATION', desc: lang === 'sr' ? 'Vrati se na glavnu stranicu sa vestima.' : 'Врати се на главната страница со вести.' },
    { id: 'act-briefing', label: lang === 'sr' ? 'Dnevni Brifing' : 'Дневен Брифинг', icon: Zap, href: lang === 'sr' ? '/briefing' : '/mk/briefing', category: 'NAVIGATION', desc: lang === 'sr' ? 'Pregled najvažnijih vesti u formi brifinga.' : 'Преглед на најважните вести во форма на брифинг.' },
    { id: 'act-foryou', label: lang === 'sr' ? 'Za Vas' : 'За Вас', icon: Compass, href: lang === 'sr' ? '/for-you' : '/mk/for-you', category: 'NAVIGATION', desc: lang === 'sr' ? 'Personalizovan pregled vesti prema vašim interesovanjima.' : 'Персонализиран преглед на вести според вашите интереси.' },
    { id: 'act-pulse', label: lang === 'sr' ? 'Informativni Ritam' : 'Информативен Ритам', icon: Activity, href: lang === 'sr' ? '/pulse' : '/mk/pulse', category: 'NAVIGATION', desc: lang === 'sr' ? 'Pratite trendove i medijski pluralizam.' : 'Следете ги трендовите и медиумскиот плурализам.' },
    { id: 'act-archive', label: lang === 'sr' ? 'Arhiva vesti' : 'Архива на вести', icon: Archive, href: lang === 'sr' ? '/archive' : '/mk/archive', category: 'NAVIGATION', desc: lang === 'sr' ? 'Pretražite sve dosadašnje objave.' : 'Пребарајте ги сите досегашни објави.' },
    { id: 'act-about', label: lang === 'sr' ? 'O Projektu' : 'За Проектот', icon: HelpCircle, href: lang === 'sr' ? '/about' : '/mk/about', category: 'HELP', desc: lang === 'sr' ? 'Saznajte više o Preseku i tehnologiji iza njega.' : 'Дознајте повеќе за Пресек и технологијата зад него.' },
  ];

  const CATEGORIES = [
    { id: 'all', label: lang === 'sr' ? 'SVE TEME' : 'СИТЕ ТЕМИ', color: 'bg-nyt-accent' },
    { id: lang === 'sr' ? 'Srbija' : 'Makedonija', label: lang === 'sr' ? 'Srbija' : 'Македонија', color: 'bg-nyt-red' },
    { id: 'Politika', label: lang === 'sr' ? 'Politika' : 'Политика', color: 'bg-blue-600' },
    { id: 'Ekonomija', label: lang === 'sr' ? 'Ekonomija' : 'Економија', color: 'bg-emerald-600' },
    { id: 'Sport', label: lang === 'sr' ? 'Sport' : 'Спорт', color: 'bg-orange-500' },
    { id: 'Kultura', label: lang === 'sr' ? 'Kultura' : 'Култура', color: 'bg-purple-600' },
    { id: 'Tehnologija', label: lang === 'sr' ? 'Tehnologija' : 'Технологија', color: 'bg-cyan-600' },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
        setPlaceholderIdx((prev) => (prev + 1) % placeholders.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [placeholders.length]);

  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (initialQuery !== undefined && initialQuery !== null && query !== initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery, query]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const saved = localStorage.getItem('presek_recent_searches');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const loaded = Array.isArray(parsed) && parsed.length > 0 && typeof parsed[0] === 'string'
          ? parsed.map((q: string) => ({ query: q, timestamp: Date.now() }))
          : parsed;
        setRecentSearches(loaded.slice(0, 5) || []);
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

  const startVoiceSearch = useCallback(() => {
    if (typeof window === 'undefined' || !('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      return;
    }
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = lang === 'sr' ? 'sr-RS' : 'mk-MK';
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognition.onerror = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setQuery(transcript);
        setIsListening(false);
      }
    };
    recognition.start();
  }, [lang]);

  const stopVoiceSearch = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (e) {
        console.error(e);
      }
    }
    setIsListening(false);
  };

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (!isOpen) {
      document.body.style.overflow = 'unset';
      setActiveIndex(-1);
      setSuggestions([]);
      setError(null);
      return;
    }
    lastFocusedRef.current = document.activeElement as HTMLElement;
    document.body.style.overflow = 'hidden';
    const timer = setTimeout(() => {
      if (inputRef.current) inputRef.current.focus();
    }, 100);
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
        const res = await fetch(`/api/trending?lang=${lang}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data)) {
          setTrendingItems(data.slice(0, 10));
        }
      } catch {
        if (!cancelled) setTrendingItems([]);
      }
    };
    loadTrending();
    return () => { cancelled = true; };
  }, [isOpen, lang]);

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
        const url = `/api/news?q=${encodeURIComponent(trimmed)}&page_size=12&lang=${lang}`;
        const timespanPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
        const categoryPart = categoryFilter !== 'all' ? `&category=${encodeURIComponent(categoryFilter)}` : '';
        const res = await fetch(url + timespanPart + categoryPart);
        if (!res.ok) throw new Error(lang === 'sr' ? 'Greška pri pretraživanju.' : 'Грешка при пребарувањето.');
        const data = await res.json();
        const nextSuggestions = Array.isArray(data?.clusters)
          ? data.clusters.map((cluster: any) => {
              const article = cluster.articles?.[0] || {};
              return {
                cluster_id: cluster.cluster_id,
                title: getDisplayTitle(article, lang === 'sr' ? 'Naslov' : 'Наслов'),
                image_url: cluster.representative_image || article.image_url || null,
                source: article.source || '',
                category: article.category || '',
                description: getDisplaySummary(article),
                sourceCount: cluster.articles?.length || 0,
                pulse_score: cluster.pulse_score,
                has_synthesis: cluster.has_synthesis,
                matchLabel: cluster.is_breaking ? (lang === 'sr' ? 'HITNO' : 'ИТНО') : 'vest',
              };
            })
          : [];

        if (!cancelled) {
          setSuggestions(nextSuggestions);
          setEntityResult(data.entity || null);
          setActiveIndex(nextSuggestions.length > 0 ? 0 : -1);
        }
      } catch (err) {
        if (!cancelled) {
          setSuggestions([]);
          setEntityResult(null);
          setError(err instanceof Error ? err.message : (lang === 'sr' ? 'Greška' : 'Грешка'));
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 200);

    return () => {
      cancelled = true;
      if (typeof window !== 'undefined') window.clearTimeout(timer);
    };
  }, [query, isOpen, timespan, categoryFilter, lang]);

  const closeSearch = () => setIsOpen(false);

  const persistRecentSearch = (searchQuery: string) => {
    const cleanQuery = searchQuery.trim();
    if (!cleanQuery) return;
    const newRecent = [{ query: cleanQuery, timestamp: Date.now() }, ...recentSearches.filter((s) => s.query !== cleanQuery).slice(0, 4)];
    setRecentSearches(newRecent);
    if (typeof window !== 'undefined') localStorage.setItem('presek_recent_searches', JSON.stringify(newRecent));
  };

  const navigateToQuery = (searchQuery: string) => {
    const cleanQuery = searchQuery.trim();
    if (!cleanQuery) return;
    persistRecentSearch(cleanQuery);
    closeSearch();
    const tsPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
    const catPart = categoryFilter !== 'all' ? `&category=${encodeURIComponent(categoryFilter)}` : '';
    const prefix = lang === 'sr' ? '' : '/mk';
    navigate(`${prefix}/?q=${encodeURIComponent(cleanQuery)}${tsPart}${catPart}`);
  };

  const navigateToCluster = (clusterId: string) => {
    if (!clusterId) return;
    closeSearch();
    const prefix = lang === 'sr' ? '' : '/mk';
    navigate(`${prefix}/cluster/${clusterId}`);
  };

  const onDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const max = suggestions.length + (entityResult ? 1 : 0) + filteredActions.length;
      setActiveIndex((prev) => (prev + 1) % max);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const max = suggestions.length + (entityResult ? 1 : 0) + filteredActions.length;
      setActiveIndex((prev) => (prev <= 0 ? max - 1 : prev - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex === -1) {
        navigateToQuery(query);
      } else if (entityResult && activeIndex === 0) {
        navigateToQuery(entityResult.name);
      } else {
        const adjustedIndex = entityResult ? activeIndex - 1 : activeIndex;
        if (adjustedIndex >= 0 && adjustedIndex < suggestions.length) {
          navigateToCluster(suggestions[adjustedIndex].cluster_id);
        } else {
          const actionIndex = adjustedIndex - suggestions.length;
          const action = filteredActions[actionIndex];
          if (action) { closeSearch(); navigate(action.href); }
        }
      }
    }
  };

  const filteredActions = SEARCH_ACTIONS.filter(a =>
    a.label.toLowerCase().includes(query.toLowerCase()) ||
    a.desc.toLowerCase().includes(query.toLowerCase())
  );

  const selectedItem = (entityResult && activeIndex === 0)
    ? { type: 'ENTITY' as const, data: entityResult }
    : (activeIndex >= (entityResult ? 1 : 0) && activeIndex < (entityResult ? 1 : 0) + suggestions.length)
      ? { type: 'CLUSTER' as const, data: suggestions[entityResult ? activeIndex - 1 : activeIndex] }
      : (activeIndex >= (entityResult ? 1 : 0) + suggestions.length)
        ? { type: 'ACTION' as const, data: filteredActions[activeIndex - (entityResult ? 1 : 0) - suggestions.length] }
        : null;

  const overlayContent = isOpen && (
    <div
      className="fixed inset-0 z-[10000] bg-background/95 backdrop-blur-2xl flex items-center justify-center transition-all animate-in fade-in duration-300"
      role="dialog"
      aria-modal="true"
      onKeyDown={onDialogKeyDown}
      onClick={closeSearch}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-6xl h-[100dvh] sm:h-[92vh] md:h-[80vh] bg-background/95 border-x border-border/50 sm:border sm:border-border/50 shadow-2xl rounded-none sm:rounded-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 mx-0 sm:mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Command Header */}
        <div className="flex items-center gap-3 px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/10">
          <Search className="hidden sm:block text-nyt-accent" size={24} />
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              data-testid="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={lang === 'sr' ? "Pretražite vesti, teme ili subjekte..." : "Пребарај вести, теми или субјекти..."}
              className="w-full bg-transparent py-2.5 sm:py-4 text-xl sm:text-2xl md:text-3xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 border-b-2 border-transparent focus:border-nyt-accent transition-colors"
              autoComplete="off"
              spellCheck="false"
            />
            {isLoading && (
              <div className="absolute right-0 top-1/2 -translate-y-1/2">
                <LoaderCircle size={20} className="animate-spin text-nyt-accent" />
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 sm:gap-[var(--grid-gap)]">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`p-2 rounded-lg hover:bg-secondary transition-colors ${showFilters ? 'text-nyt-accent' : 'text-muted-foreground'}`}
              title={lang === 'sr' ? 'Filteri pretrage' : 'Филтри за пребарување'}
            >
              <SlidersHorizontal size={18} />
            </button>
            <button onClick={startVoiceSearch} className={`p-2 rounded-lg hover:bg-secondary transition-colors ${isListening ? 'text-nyt-accent animate-pulse' : 'text-muted-foreground'}`}>
              <Mic size={18} />
            </button>
            <button onClick={closeSearch} className="p-2 rounded-lg hover:bg-secondary text-muted-foreground transition-colors">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Voice Search listening overlay */}
        {isListening && (
          <div className="absolute inset-0 bg-background/95 backdrop-blur-md z-[10001] flex flex-col items-center justify-center gap-6 animate-in fade-in duration-300">
            <div className="w-20 h-20 bg-nyt-accent/10 rounded-full flex items-center justify-center text-nyt-accent animate-pulse border border-nyt-accent/20 shadow-lg shadow-nyt-accent/10">
              <Mic size={36} />
            </div>
            
            <div className="flex items-center gap-1.5 h-10 justify-center">
              {[...Array(6)].map((_, i) => (
                <div
                  key={i}
                  className="w-1.5 bg-nyt-accent rounded-full animate-bounce"
                  style={{
                    height: '24px',
                    animationDelay: `${i * 0.15}s`,
                    animationDuration: '0.8s'
                  }}
                />
              ))}
            </div>
            
            <p className="font-serif font-black text-xl text-center">
              {lang === 'sr' ? 'Slušam vas...' : 'Ве слушам...'}
            </p>
            
            <button
              onClick={stopVoiceSearch}
              className="px-6 py-2.5 bg-secondary hover:bg-secondary-foreground/10 border border-border rounded-full text-xs font-black uppercase tracking-widest transition-all"
            >
              {lang === 'sr' ? 'Otkaži' : 'Откажи'}
            </button>
          </div>
        )}

        {/* Filters Collapsible Panel */}
        {showFilters && (
          <div className="px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/15 flex flex-col md:flex-row gap-4 md:items-center animate-in slide-in-from-top-4 duration-300">
            {/* Category Filter */}
            <div className="flex-1">
              <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground block mb-2">
                {lang === 'sr' ? 'Tema' : 'Тема'}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setCategoryFilter(cat.id)}
                    className={`px-3 py-1 text-[11px] font-bold rounded-full transition-all border ${
                      categoryFilter === cat.id
                        ? 'bg-nyt-accent text-white border-nyt-accent shadow-sm'
                        : 'bg-background hover:bg-secondary border-border text-foreground'
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Timespan Filter */}
            <div className="shrink-0">
              <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground block mb-2">
                {lang === 'sr' ? 'Vremenski okvir' : 'Временска рамка'}
              </span>
              <div className="flex gap-1.5">
                {[
                  { id: 'all', label: lang === 'sr' ? 'Sve vreme' : 'Сите времиња' },
                  { id: '24h', label: lang === 'sr' ? 'Danas' : 'Денес' },
                  { id: '7d', label: lang === 'sr' ? 'Zadnjih 7 dana' : 'Задните 7 дена' },
                  { id: '30d', label: lang === 'sr' ? 'Zadnjih 30 dana' : 'Задните 30 дена' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTimespan(t.id)}
                    className={`px-3 py-1 text-[11px] font-bold rounded-full transition-all border ${
                      timespan === t.id
                        ? 'bg-nyt-accent text-white border-nyt-accent shadow-sm'
                        : 'bg-background hover:bg-secondary border-border text-foreground'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Main Content Area */}
        <div className="flex-1 overflow-hidden flex">
          {/* Left Column: Results List */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 sm:space-y-8 scroll-smooth lg:border-r lg:border-border/40 custom-scrollbar">

            {/* Empty State / Initial View */}
            {!query.trim() && (
              <div className="space-y-6 sm:space-y-10">
                {recentSearches.length > 0 && (
                  <section>
                    <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                       <History size={12} /> {lang === 'sr' ? 'POSLEDNJE PRETRAGE' : 'ПОСЛЕДНИ ПРЕБАРУВАЊА'}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {recentSearches.map((s, i) => (
                        <div
                          key={i}
                          onClick={() => setQuery(s.query)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary/50 hover:bg-secondary border border-border/50 rounded-full text-[11px] sm:text-xs font-bold transition-all cursor-pointer group/pill"
                        >
                          <span>{s.query}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              const newRecent = recentSearches.filter((item) => item.query !== s.query);
                              setRecentSearches(newRecent);
                              if (typeof window !== 'undefined') {
                                localStorage.setItem('presek_recent_searches', JSON.stringify(newRecent));
                              }
                            }}
                            className="p-0.5 rounded-full hover:bg-muted-foreground/20 text-muted-foreground/40 hover:text-muted-foreground/80 transition-colors"
                            title={lang === 'sr' ? 'Ukloni pretragu' : 'Отстрани го пребарувањето'}
                          >
                            <X size={10} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                <section>
                  <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                     <TrendingUp size={12} /> {lang === 'sr' ? 'TREND TEME' : 'ТРЕНД ТЕМИ'}
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2 sm:gap-[var(--grid-gap)]">
                    {trendingItems.length > 0 ? trendingItems.map((item, i) => (
                      <button key={i} onClick={() => setQuery(item.word)} className="flex items-center gap-2 sm:gap-[var(--grid-gap)] p-2.5 sm:p-3 bg-secondary/30 hover:bg-secondary/60 rounded-xl transition-all group text-left">
                        <span className="text-[10px] font-black text-nyt-accent/40 group-hover:text-nyt-accent">{(i+1).toString().padStart(2, '0')}</span>
                        <span className="font-serif font-black text-[13px] sm:text-sm truncate">{item.word}</span>
                      </button>
                    )) : [1,2,3,4,5,6].map(i => <div key={i} className="h-12 bg-secondary/20 animate-pulse rounded-xl"></div>)}
                  </div>
                </section>

                <section>
                  <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                     <Zap size={12} /> {lang === 'sr' ? 'BRZE AKCIJE' : 'БРЗИ АКЦИИ'}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-[var(--grid-gap)]">
                    {SEARCH_ACTIONS.map(action => (
                      <button key={action.id} onClick={() => { closeSearch(); navigate(action.href); }} className="flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 bg-secondary/30 hover:bg-secondary/60 border border-border/50 rounded-xl transition-all group text-left">
                        <div className="p-2 bg-background rounded-lg text-muted-foreground group-hover:text-nyt-accent group-hover:bg-nyt-accent/10 transition-all">
                          <action.icon size={18} />
                        </div>
                        <div>
                          <p className="text-[11px] sm:text-xs font-black uppercase tracking-wider">{action.label}</p>
                          <p className="text-[10px] text-muted-foreground line-clamp-1">{action.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* Results List */}
            {query.trim().length >= 2 && (
              <div className="space-y-6 sm:space-y-8">
                {entityResult && (
                  <section>
                    <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4">{lang === 'sr' ? 'SUBJEKTI' : 'СУБЈЕКТИ'}</h3>
                    <button
                      onClick={() => navigateToQuery(entityResult.name)}
                      className={`w-full flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-xl border transition-all text-left ${activeIndex === 0 ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                    >
                      <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full overflow-hidden bg-secondary flex items-center justify-center shrink-0 border-2 border-nyt-accent/20">
                        {entityResult.image_url ? (
                          <img src={`/proxy?url=${encodeURIComponent(entityResult.image_url)}&w=128`} className="w-full h-full object-cover" />
                        ) : (
                          <User size={24} className="text-nyt-accent" />
                        )}
                      </div>
                      <div>
                        <p className="font-serif font-black text-lg sm:text-xl">{highlightMatch(entityResult.name, query)}</p>
                        <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{entityResult.type} · {entityResult.total_mentions} {lang === 'sr' ? 'pominjanja' : 'споменувања'}</p>
                      </div>
                      <ArrowUpRight size={16} className="ml-auto text-muted-foreground" />
                    </button>
                  </section>
                )}

                {suggestions.length > 0 && (
                  <section>
                    <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4">{lang === 'sr' ? 'VESTI I PRIČE' : 'ВЕСТИ И ПРИКАЗНИ'}</h3>
                    <div className="space-y-2">
                      {suggestions.map((item, idx) => {
                        const globalIdx = entityResult ? idx + 1 : idx;
                        return (
                          <button
                            key={item.cluster_id}
                            onClick={() => navigateToCluster(item.cluster_id)}
                            className={`w-full flex items-start gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-xl border transition-all text-left group ${
                              item.has_synthesis
                                ? 'bg-amber-500/5 border-amber-500/10 hover:border-amber-500/30'
                                : 'bg-transparent border-transparent hover:bg-secondary/30'
                            } ${activeIndex === globalIdx ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : ''}`}
                          >
                            <div className="w-14 sm:w-16 aspect-[4/3] rounded-lg overflow-hidden bg-secondary shrink-0 border border-border/50">
                              {item.image_url && <img src={`/proxy?url=${encodeURIComponent(item.image_url)}&w=200`} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className={`text-[9px] font-black uppercase tracking-wider ${item.has_synthesis ? 'text-amber-600 dark:text-amber-400' : 'text-nyt-accent'}`}>{item.category}</span>
                                {item.has_synthesis && (
                                  <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[8px] font-black uppercase tracking-wider">
                                    <Sparkles size={8} fill="currentColor" />
                                    {lang === 'sr' ? 'Sinteza' : 'Синтеза'}
                                  </span>
                                )}
                              </div>
                              <p className="font-serif font-black text-base sm:text-lg leading-tight line-clamp-2 group-hover:text-nyt-accent transition-colors">{highlightMatch(item.title, query)}</p>
                              <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)] mt-1.5 sm:mt-2 text-[9px] font-black uppercase tracking-widest text-muted-foreground/60">
                                <span>{item.source}</span>
                                <span>{item.sourceCount} {item.sourceCount === 1 ? (lang === 'sr' ? 'izvor' : 'извор') : (lang === 'sr' ? 'izvora' : 'извори')}</span>
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                )}

                {filteredActions.length > 0 && (
                  <section>
                    <h3 className="text-[9px] sm:text-[10px] font-black uppercase tracking-[0.18em] sm:tracking-[0.2em] text-muted-foreground mb-3 sm:mb-4">{lang === 'sr' ? 'AKCIJE' : 'АКЦИИ'}</h3>
                    <div className="grid grid-cols-1 gap-[var(--grid-gap)]">
                      {filteredActions.map((action, idx) => {
                        const globalIdx = (entityResult ? 1 : 0) + suggestions.length + idx;
                        return (
                          <button
                            key={action.id}
                            onClick={() => { closeSearch(); navigate(action.href); }}
                            className={`w-full flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 rounded-xl border transition-all text-left ${activeIndex === globalIdx ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                          >
                            <div className="p-2 bg-secondary rounded-lg text-muted-foreground">
                              <action.icon size={16} />
                            </div>
                            <span className="text-[11px] sm:text-xs font-black uppercase tracking-wider">{action.label}</span>
                            <span className="hidden sm:inline text-[10px] text-muted-foreground opacity-60">→ {action.href}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                )}

                {!isLoading && suggestions.length === 0 && !entityResult && filteredActions.length === 0 && (
                  <div className="py-14 sm:py-20 flex flex-col items-center text-center">
                    <div className="w-14 h-14 sm:w-16 sm:h-16 bg-secondary/50 rounded-full flex items-center justify-center mb-5 sm:mb-6">
                       <Search size={32} className="text-muted-foreground/30" />
                    </div>
                    <h4 className="font-serif font-black text-xl sm:text-2xl mb-2">{lang === 'sr' ? `Nema rezultata za "${query}"` : `Нема резултати за "${query}"`}</h4>
                    <p className="text-muted-foreground text-[13px] sm:text-sm max-w-xs">{lang === 'sr' ? 'Pokušajte sa konkretnijim ključnim rečima ili prelistajte aktuelne trendove.' : 'Обидете се со поконкретни клучни зборови или прелистајте ги актуелните трендови.'}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Column: Preview Panel (Desktop Only) */}
          <div className="hidden lg:flex w-[400px] bg-secondary/5 border-l border-border/40 p-8 flex-col overflow-y-auto">
            {selectedItem ? (
              <div className="animate-in fade-in slide-in-from-right-4 duration-300">
                {selectedItem.type === 'CLUSTER' && (
                  <div className="space-y-6">
                    <div className="aspect-[16/9] rounded-xl overflow-hidden bg-secondary border border-border shadow-sm">
                      {selectedItem.data.image_url && <img src={`/proxy?url=${encodeURIComponent(selectedItem.data.image_url)}&w=600`} className="w-full h-full object-cover" />}
                    </div>

                    <div>
                      <div className="flex items-center gap-2 mb-3">
                         <span className="px-2 py-1 bg-nyt-accent text-white text-[9px] font-black uppercase tracking-widest rounded">{selectedItem.data.category}</span>
                         {selectedItem.data.has_synthesis && (
                           <span className="px-2 py-1 bg-gradient-to-r from-amber-500 to-amber-600 text-white text-[9px] font-black uppercase tracking-widest rounded flex items-center gap-1 shadow-sm shadow-amber-500/20">
                             <Sparkles size={10} fill="currentColor" />
                             {lang === 'sr' ? 'AI SINTEZA' : 'AI СИНТЕЗА'}
                           </span>
                         )}
                         <span className="text-[9px] font-black uppercase tracking-[0.2em] text-muted-foreground flex items-center gap-1"><Clock size={12} /> {lang === 'sr' ? 'PRE 2 ČASA' : 'ПРЕД 2 ЧАСА'}</span>
                      </div>
                      <h2 className="font-serif font-black text-2xl leading-tight mb-4">{selectedItem.data.title}</h2>
                      <p className="text-base text-muted-foreground leading-relaxed font-nyt-body line-clamp-6">{selectedItem.data.description}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-[var(--grid-gap)] py-6 border-y border-border/40">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">{lang === 'sr' ? 'izvori' : 'извори'}</p>
                        <p className="text-xl font-black">{selectedItem.data.sourceCount}</p>
                      </div>
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">{lang === 'sr' ? 'SKOR' : 'СКОР'}</p>
                        <p className="text-xl font-black text-nyt-accent">{selectedItem.data.pulse_score || '8.2'}</p>
                      </div>
                    </div>

                    <button
                      onClick={() => navigateToCluster(selectedItem.data.cluster_id)}
                      className="w-full py-4 bg-nyt-accent text-white rounded-xl font-black uppercase tracking-[0.2em] text-xs shadow-lg shadow-nyt-accent/20 hover:scale-[1.02] transition-all flex items-center justify-center gap-[var(--grid-gap)]"
                    >
                      {lang === 'sr' ? 'OTVORI PRIČU' : 'ОТВОРИ ПРИКАЗНА'} <ChevronRight size={16} />
                    </button>
                  </div>
                )}

                {selectedItem.type === 'ENTITY' && (
                  <div className="space-y-8">
                    <div className="flex flex-col items-center text-center">
                      <div className="w-32 h-32 rounded-full overflow-hidden border-4 border-nyt-accent/10 mb-6 bg-secondary flex items-center justify-center">
                        {selectedItem.data.image_url ? (
                          <img src={`/proxy?url=${encodeURIComponent(selectedItem.data.image_url)}&w=256`} className="w-full h-full object-cover" />
                        ) : (
                          <User size={64} className="text-nyt-accent/40" />
                        )}
                      </div>
                      <h2 className="font-serif font-black text-3xl mb-2">{selectedItem.data.name}</h2>
                      <p className="px-4 py-1.5 bg-secondary border border-border rounded-full text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground">{selectedItem.data.type}</p>
                    </div>

                    <div className="space-y-4">
                       <div className="p-4 bg-background border border-border rounded-xl">
                          <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-4">{lang === 'sr' ? 'MEDIJSKO PRISUSTVO' : 'МЕДИУМСКО ПРИСУСТВО'}</p>
                          <div className="flex items-end gap-1 h-12 mb-2">
                            {[30, 50, 40, 80, 60, 90, 75, 85].map((h, i) => (
                              <div key={i} className="flex-1 bg-nyt-accent/20 rounded-t-sm group relative" style={{ height: `${h}%` }}>
                                <div className="absolute inset-0 bg-nyt-accent opacity-0 group-hover:opacity-100 transition-opacity rounded-t-sm" />
                              </div>
                            ))}
                          </div>
                          <p className="text-xs font-bold">{selectedItem.data.total_mentions} {lang === 'sr' ? 'pominjanja u arhivi' : 'споменувања во архивата'}</p>
                       </div>

                       <div className="p-4 bg-background border border-border rounded-xl flex items-center justify-between">
                          <div>
                            <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">SENTIMENT</p>
                            <p className="font-serif font-black text-lg text-emerald-600">{lang === 'sr' ? 'POZITIVAN' : 'ПОЗИТИВЕН'}</p>
                          </div>
                          <Activity size={24} className="text-emerald-500" />
                       </div>
                    </div>

                    <button
                      onClick={() => navigateToQuery(selectedItem.data.name)}
                      className="w-full py-4 bg-foreground text-background rounded-xl font-black uppercase tracking-[0.2em] text-xs hover:bg-nyt-accent hover:text-white transition-all flex items-center justify-center gap-[var(--grid-gap)]"
                    >
                      {lang === 'sr' ? 'VIDI SVE VESTI' : 'ВИДИ СИТЕ ВЕСТИ'} <ExternalLink size={16} />
                    </button>
                  </div>
                )}

                {selectedItem.type === 'ACTION' && (
                  <div className="h-full flex flex-col justify-center items-center text-center space-y-6">
                    <div className="w-24 h-24 bg-nyt-accent/10 rounded-3xl flex items-center justify-center text-nyt-accent rotate-3">
                       <selectedItem.data.icon size={48} />
                    </div>
                    <div>
                      <h2 className="font-serif font-black text-3xl mb-2">{selectedItem.data.label}</h2>
                      <p className="text-muted-foreground text-sm max-w-[280px] leading-relaxed">{selectedItem.data.desc}</p>
                    </div>
                    <button
                      onClick={() => { closeSearch(); navigate(selectedItem.data.href); }}
                      className="px-10 py-4 bg-foreground text-background rounded-xl font-black uppercase tracking-[0.2em] text-xs hover:bg-nyt-accent transition-all"
                    >
                      {lang === 'sr' ? 'IZVRŠI AKCIJU' : 'ИЗВРШИ АКЦИЈА'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-30 select-none">
                <div className="w-20 h-20 border-2 border-dashed border-muted-foreground rounded-full flex items-center justify-center mb-6">
                   <Layout size={32} />
                </div>
                <p className="font-serif font-black text-xl mb-1">{lang === 'sr' ? 'Pregled' : 'Преглед'}</p>
                <p className="text-[10px] font-black uppercase tracking-widest">{lang === 'sr' ? 'Izaberite stavku za detalje' : 'Изберете ставка за детали'}</p>
              </div>
            )}
          </div>
        </div>

        {/* Command Footer */}
        <div className="px-4 sm:px-6 py-2.5 sm:py-3 border-t border-border/40 bg-secondary/5 flex items-center justify-between text-[9px] sm:text-[10px] font-black uppercase tracking-[0.14em] sm:tracking-widest text-muted-foreground/60">
           <div className="hidden sm:flex items-center gap-[var(--grid-gap)]">
              <span className="flex items-center gap-[var(--grid-gap)]"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ENTER</kbd> {lang === 'sr' ? 'IZABERI' : 'ИЗБЕРИ'}</span>
              <span className="flex items-center gap-[var(--grid-gap)]"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">↑</kbd><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">↓</kbd> {lang === 'sr' ? 'NAVIGACIJA' : 'НАВИГАЦИЈА'}</span>
              <span className="flex items-center gap-[var(--grid-gap)]"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ESC</kbd> {lang === 'sr' ? 'ZATVORI' : 'ЗАТВОРИ'}</span>
           </div>
           <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)]">
              <span className="flex items-center gap-1.5"><Globe size={12} /> {lang === 'sr' ? 'GLOBALNA PRETRAGA' : 'ГЛОБАЛНО ПРЕБАРУВАЊЕ'}</span>
              <span className="hidden sm:inline w-1 h-1 rounded-full bg-border" />
              <span className="hidden sm:flex items-center gap-1.5"><Sparkles size={12} /> AI {lang === 'sr' ? 'ASISTENCIJA' : 'АСИСТЕНЦИЈА'}</span>
           </div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(true)}
        data-testid="search-trigger"
        className="flex items-center gap-[var(--grid-gap)] px-3 py-1.5 bg-secondary/30 hover:bg-secondary/60 border border-border/60 hover:border-nyt-accent/30 rounded-lg transition-all group w-full text-left backdrop-blur-sm"
        aria-label="Otvori komanden centar"
      >
        <Search size={14} className="shrink-0 text-muted-foreground group-hover:text-nyt-accent transition-colors" />
        <span className="hidden min-w-0 flex-1 overflow-hidden h-4 sm:block">
            <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/50 group-hover:text-muted-foreground transition-colors animate-in slide-in-from-bottom-2 duration-300 block truncate">
                {placeholders[placeholderIdx]}
            </span>
        </span>
        <kbd className="hidden lg:flex items-center gap-1 px-1.5 py-0.5 bg-background/50 border border-border rounded text-[8px] font-black text-muted-foreground/40 group-hover:text-muted-foreground/60 transition-colors">
            <span className="text-[10px]">⌘</span>K
        </kbd>
      </button>

      {typeof document !== 'undefined' ? createPortal(overlayContent, document.body) : null}

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(var(--border), 0.2);
          border-radius: 0px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(var(--nyt-accent), 0.4);
        }
      `}} />
    </>
  );
}
