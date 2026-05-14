import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { navigate } from 'astro:transitions/client';
import { 
  Search, X, Zap, ArrowUpRight, LoaderCircle, Newspaper, 
  Mic, Clock, TrendingUp, User, Layout, 
  HelpCircle, Archive, Sparkles, ChevronRight,
  Globe, ShieldCheck, Activity, BookOpen, ExternalLink,
  History
} from 'lucide-react';
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

const SEARCH_ACTIONS: SearchAction[] = [
  { id: 'act-home', label: 'Почетна Страница', icon: Layout, href: '/', category: 'NAVIGATION', desc: 'Врати се на главната страница со вести.' },
  { id: 'act-briefing', label: 'Дневен Брифинг', icon: Zap, href: '/briefing', category: 'NAVIGATION', desc: 'Преглед на најважните вести во форма на брифинг.' },
  { id: 'act-pulse', label: 'Информативен Ритам', icon: Activity, href: '/pulse', category: 'NAVIGATION', desc: 'Следете ги трендовите и медиумскиот плурализам.' },
  { id: 'act-archive', label: 'Архива на вести', icon: Archive, href: '/archive', category: 'NAVIGATION', desc: 'Пребарајте ги сите досегашни објави.' },
  { id: 'act-about', label: 'За Проектот', icon: HelpCircle, href: '/about', category: 'HELP', desc: 'Дознајте повеќе за Пресек и технологијата зад него.' },
];

const CATEGORIES = [
  { id: 'all', label: 'СИТЕ ТЕМИ', color: 'bg-nyt-accent' },
  { id: 'Makedonija', label: 'Македонија', color: 'bg-nyt-red' },
  { id: 'Politika', label: 'Политика', color: 'bg-blue-600' },
  { id: 'Ekonomija', label: 'Економија', color: 'bg-emerald-600' },
  { id: 'Sport', label: 'Спорт', color: 'bg-orange-500' },
  { id: 'Kultura', label: 'Култура', color: 'bg-purple-600' },
  { id: 'Tehnologija', label: 'Технологија', color: 'bg-cyan-600' },
];

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export default function SearchIsland({ initialQuery = '' }: { initialQuery?: string | null }) {
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

  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const placeholders = [
    "Истражи ја медиумската архива...",
    "Анализирај ги противречните ставови...",
    "Деконструирај ги фактите и бројките...",
    "Мапирај ги реакциите и последиците...",
    "Што се случува во Србија?"
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (initialQuery !== undefined && initialQuery !== null && query !== initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

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
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'mk-MK';
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setQuery(transcript);
        setIsListening(false);
      }
    };
    recognition.start();
  }, []);

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
        const res = await fetch('/api/trending');
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
        const url = `/api/news?q=${encodeURIComponent(trimmed)}&page_size=12`;
        const timespanPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
        const categoryPart = categoryFilter !== 'all' ? `&category=${encodeURIComponent(categoryFilter)}` : '';
        const res = await fetch(url + timespanPart + categoryPart);
        if (!res.ok) throw new Error('Грешка при пребарувањето.');
        const data = await res.json();
        const nextSuggestions = Array.isArray(data?.clusters)
          ? data.clusters.map((cluster: any) => {
              const article = cluster.articles?.[0] || {};
              return {
                cluster_id: cluster.cluster_id,
                title: getDisplayTitle(article, 'Наслов'),
                image_url: cluster.representative_image || article.image_url || null,
                source: article.source || '',
                category: article.category || '',
                description: getDisplaySummary(article),
                sourceCount: cluster.articles?.length || 0,
                pulse_score: cluster.pulse_score,
                has_synthesis: cluster.has_synthesis,
                matchLabel: cluster.is_breaking ? 'ИТНО' : 'вест',
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
          setError(err instanceof Error ? err.message : 'Грешка');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 200);

    return () => {
      cancelled = true;
      if (typeof window !== 'undefined') window.clearTimeout(timer);
    };
  }, [query, isOpen, timespan, categoryFilter]);

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
    navigate(`/?q=${encodeURIComponent(cleanQuery)}${tsPart}${catPart}`);
  };

  const navigateToCluster = (clusterId: string) => {
    if (!clusterId) return;
    closeSearch();
    navigate(`/cluster/${clusterId}`);
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
    ? { type: 'ENTITY', data: entityResult } 
    : (activeIndex >= (entityResult ? 1 : 0) && activeIndex < (entityResult ? 1 : 0) + suggestions.length)
      ? { type: 'CLUSTER', data: suggestions[entityResult ? activeIndex - 1 : activeIndex] }
      : (activeIndex >= (entityResult ? 1 : 0) + suggestions.length)
        ? { type: 'ACTION', data: filteredActions[activeIndex - (entityResult ? 1 : 0) - suggestions.length] }
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
        className="w-full max-w-6xl h-[90vh] md:h-[80vh] bg-background/95 border border-border/50 shadow-2xl rounded-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Command Header */}
        <div className="flex items-center gap-4 px-6 py-4 border-b border-border/40 bg-secondary/10">
          <Search className="text-nyt-accent" size={24} />
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Prebarajte vesti, temi ili subjekti..."
              className="w-full bg-transparent py-4 text-2xl md:text-3xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 border-b-2 border-transparent focus:border-nyt-accent transition-colors"
              autoComplete="off"
              spellCheck="false"
            />
            {isLoading && (
              <div className="absolute right-0 top-1/2 -translate-y-1/2">
                <LoaderCircle size={20} className="animate-spin text-nyt-accent" />
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={startVoiceSearch} className={`p-2 rounded-lg hover:bg-secondary transition-colors ${isListening ? 'text-nyt-accent animate-pulse' : 'text-muted-foreground'}`}>
              <Mic size={20} />
            </button>
            <button onClick={closeSearch} className="p-2 rounded-lg hover:bg-secondary text-muted-foreground transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-hidden flex">
          {/* Left Column: Results List */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-8 scroll-smooth border-r border-border/40 custom-scrollbar">
            
            {/* Empty State / Initial View */}
            {!query.trim() && (
              <div className="space-y-10">
                {recentSearches.length > 0 && (
                  <section>
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4 flex items-center gap-2">
                       <History size={12} /> ПОСЛЕДНИ ПРЕБАРУВАЊА
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {recentSearches.map((s, i) => (
                        <button key={i} onClick={() => setQuery(s.query)} className="px-4 py-2 bg-secondary/50 hover:bg-secondary border border-border/50 rounded-full text-xs font-bold transition-all">
                          {s.query}
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                <section>
                  <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4 flex items-center gap-2">
                     <TrendingUp size={12} /> ТРЕНД ТЕМИ
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {trendingItems.length > 0 ? trendingItems.map((item, i) => (
                      <button key={i} onClick={() => setQuery(item.word)} className="flex items-center gap-3 p-3 bg-secondary/30 hover:bg-secondary/60 rounded-xl transition-all group text-left">
                        <span className="text-[10px] font-black text-nyt-accent/40 group-hover:text-nyt-accent">{(i+1).toString().padStart(2, '0')}</span>
                        <span className="font-serif font-black text-sm truncate">{item.word}</span>
                      </button>
                    )) : [1,2,3,4,5,6].map(i => <div key={i} className="h-12 bg-secondary/20 animate-pulse rounded-xl"></div>)}
                  </div>
                </section>

                <section>
                  <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4 flex items-center gap-2">
                     <Zap size={12} /> БРЗИ АКЦИИ
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {SEARCH_ACTIONS.map(action => (
                      <button key={action.id} onClick={() => { closeSearch(); navigate(action.href); }} className="flex items-center gap-4 p-4 bg-secondary/30 hover:bg-secondary/60 border border-border/50 rounded-xl transition-all group text-left">
                        <div className="p-2 bg-background rounded-lg text-muted-foreground group-hover:text-nyt-accent group-hover:bg-nyt-accent/10 transition-all">
                          <action.icon size={20} />
                        </div>
                        <div>
                          <p className="text-xs font-black uppercase tracking-wider">{action.label}</p>
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
              <div className="space-y-8">
                {entityResult && (
                  <section>
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4">СУБЈЕКТИ</h3>
                    <button
                      onClick={() => navigateToQuery(entityResult.name)}
                      className={`w-full flex items-center gap-4 p-4 rounded-xl border transition-all text-left ${activeIndex === 0 ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                    >
                      <div className="w-12 h-12 rounded-full overflow-hidden bg-secondary flex items-center justify-center shrink-0 border-2 border-nyt-accent/20">
                        {entityResult.image_url ? (
                          <img src={`/proxy?url=${encodeURIComponent(entityResult.image_url)}&w=128`} className="w-full h-full object-cover" />
                        ) : (
                          <User size={24} className="text-nyt-accent" />
                        )}
                      </div>
                      <div>
                        <p className="font-serif font-black text-xl">{entityResult.name}</p>
                        <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{entityResult.type} · {entityResult.total_mentions} споменувања</p>
                      </div>
                      <ArrowUpRight size={16} className="ml-auto text-muted-foreground" />
                    </button>
                  </section>
                )}

                {suggestions.length > 0 && (
                  <section>
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4">ВЕСТИ И ПРИЧИ</h3>
                    <div className="space-y-2">
                      {suggestions.map((item, idx) => {
                        const globalIdx = entityResult ? idx + 1 : idx;
                        return (
                          <button
                            key={item.cluster_id}
                            onClick={() => navigateToCluster(item.cluster_id)}
                            className={`w-full flex items-start gap-4 p-4 rounded-xl border transition-all text-left group ${activeIndex === globalIdx ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                          >
                            <div className="w-16 aspect-[4/3] rounded-lg overflow-hidden bg-secondary shrink-0 border border-border/50">
                              {item.image_url && <img src={`/proxy?url=${encodeURIComponent(item.image_url)}&w=200`} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-[9px] font-black uppercase tracking-wider text-nyt-accent">{item.category}</span>
                                {item.has_synthesis && <Sparkles size={10} className="text-nyt-accent" fill="currentColor" />}
                              </div>
                              <p className="font-serif font-black text-lg leading-tight line-clamp-2 group-hover:text-nyt-accent transition-colors">{item.title}</p>
                              <div className="flex items-center gap-3 mt-2 text-[9px] font-black uppercase tracking-widest text-muted-foreground/60">
                                <span>{item.source}</span>
                                <span>{item.sourceCount} {item.sourceCount === 1 ? 'извор' : 'извори'}</span>
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
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground mb-4">АКЦИИ</h3>
                    <div className="grid grid-cols-1 gap-2">
                      {filteredActions.map((action, idx) => {
                        const globalIdx = (entityResult ? 1 : 0) + suggestions.length + idx;
                        return (
                          <button
                            key={action.id}
                            onClick={() => { closeSearch(); navigate(action.href); }}
                            className={`w-full flex items-center gap-4 p-3 rounded-xl border transition-all text-left ${activeIndex === globalIdx ? 'bg-nyt-accent/5 border-nyt-accent/30 ring-1 ring-nyt-accent/20' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                          >
                            <div className="p-2 bg-secondary rounded-lg text-muted-foreground">
                              <action.icon size={16} />
                            </div>
                            <span className="text-xs font-black uppercase tracking-wider">{action.label}</span>
                            <span className="text-[10px] text-muted-foreground opacity-60">→ {action.href}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                )}

                {!isLoading && suggestions.length === 0 && !entityResult && filteredActions.length === 0 && (
                  <div className="py-20 flex flex-col items-center text-center">
                    <div className="w-16 h-16 bg-secondary/50 rounded-full flex items-center justify-center mb-6">
                       <Search size={32} className="text-muted-foreground/30" />
                    </div>
                    <h4 className="font-serif font-black text-2xl mb-2">Нема резултати за "{query}"</h4>
                    <p className="text-muted-foreground text-sm max-w-xs">Обидете се со поконкретни клучни зборови или прелистајте ги актуелните трендови.</p>
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
                      <div className="flex items-center gap-3 mb-3">
                         <span className="px-2 py-1 bg-nyt-accent text-white text-[9px] font-black uppercase tracking-widest rounded">{selectedItem.data.category}</span>
                         <span className="text-[9px] font-black uppercase tracking-[0.2em] text-muted-foreground flex items-center gap-1"><Clock size={12} /> ПРЕД 2 ЧАСА</span>
                      </div>
                      <h2 className="font-serif font-black text-2xl leading-tight mb-4">{selectedItem.data.title}</h2>
                      <p className="text-base text-muted-foreground leading-relaxed font-nyt-body line-clamp-6">{selectedItem.data.description}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-4 py-6 border-y border-border/40">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">ИЗВОРИ</p>
                        <p className="text-xl font-black">{selectedItem.data.sourceCount}</p>
                      </div>
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">СКОР</p>
                        <p className="text-xl font-black text-nyt-accent">{selectedItem.data.pulse_score || '8.2'}</p>
                      </div>
                    </div>

                    <button
                      onClick={() => navigateToCluster(selectedItem.data.cluster_id)}
                      className="w-full py-4 bg-nyt-accent text-white rounded-xl font-black uppercase tracking-[0.2em] text-xs shadow-lg shadow-nyt-accent/20 hover:scale-[1.02] transition-all flex items-center justify-center gap-2"
                    >
                      ОТВОРИ ПРИКАЗНА <ChevronRight size={16} />
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
                          <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-4">МЕДИУМСКО ПРИСУСТВО</p>
                          <div className="flex items-end gap-1 h-12 mb-2">
                            {[30, 50, 40, 80, 60, 90, 75, 85].map((h, i) => (
                              <div key={i} className="flex-1 bg-nyt-accent/20 rounded-t-sm group relative" style={{ height: `${h}%` }}>
                                <div className="absolute inset-0 bg-nyt-accent opacity-0 group-hover:opacity-100 transition-opacity rounded-t-sm" />
                              </div>
                            ))}
                          </div>
                          <p className="text-xs font-bold">{selectedItem.data.total_mentions} споменувања во архивата</p>
                       </div>

                       <div className="p-4 bg-background border border-border rounded-xl flex items-center justify-between">
                          <div>
                            <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">СЕНТИМЕНТ</p>
                            <p className="font-serif font-black text-lg text-emerald-600">ПОЗИТИВЕН</p>
                          </div>
                          <Activity size={24} className="text-emerald-500" />
                       </div>
                    </div>

                    <button
                      onClick={() => navigateToQuery(selectedItem.data.name)}
                      className="w-full py-4 bg-foreground text-background rounded-xl font-black uppercase tracking-[0.2em] text-xs hover:bg-nyt-accent hover:text-white transition-all flex items-center justify-center gap-2"
                    >
                      ВИДИ СИТЕ ВЕСТИ <ExternalLink size={16} />
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
                      ИЗВРШИ АКЦИЈА
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-30 select-none">
                <div className="w-20 h-20 border-2 border-dashed border-muted-foreground rounded-full flex items-center justify-center mb-6">
                   <Layout size={32} />
                </div>
                <p className="font-serif font-black text-xl mb-1">Преглед</p>
                <p className="text-[10px] font-black uppercase tracking-widest">Изберете ставка за детали</p>
              </div>
            )}
          </div>
        </div>

        {/* Command Footer */}
        <div className="px-6 py-3 border-t border-border/40 bg-secondary/5 flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">
           <div className="flex items-center gap-6">
              <span className="flex items-center gap-2"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ENTER</kbd> ИЗБЕРИ</span>
              <span className="flex items-center gap-2"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">↑</kbd><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">↓</kbd> НАВИГАЦИЈА</span>
              <span className="flex items-center gap-2"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ESC</kbd> ЗАТВОРИ</span>
           </div>
           <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5"><Globe size={12} /> ГЛОБАЛНА ПРЕТРАГА</span>
              <span className="w-1 h-1 rounded-full bg-border" />
              <span className="flex items-center gap-1.5"><Sparkles size={12} /> AI АСИСТЕНЦИЈА</span>
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
        className="flex items-center gap-3 px-3 py-1.5 bg-secondary/30 hover:bg-secondary/60 border border-border/60 hover:border-nyt-accent/30 rounded-lg transition-all group w-full text-left backdrop-blur-sm"
        aria-label="Отвори команден центар"
      >
        <Search size={14} className="text-muted-foreground group-hover:text-nyt-accent transition-colors" />
        <span className="flex-1 overflow-hidden h-4 block">
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
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(var(--nyt-accent), 0.4);
        }
      `}} />
    </>
  );
}
