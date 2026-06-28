import { localePath, localePathForLang, type Locale } from '../lib/localePaths';
import { useClientTranslations } from '../i18n/clientTranslations';
import { search } from '../i18n/namespaces/search';
import { news } from '../i18n/namespaces/news';
import { common } from '../i18n/namespaces/common';
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { navigate } from 'astro:transitions/client';
import {
  Search, X, Zap, ArrowUpRight, LoaderCircle, Newspaper,
  Mic, Clock, TrendingUp, User, Layout,
  Archive, Sparkles, ChevronRight,
  Globe, ShieldCheck, Activity, BookOpen, ExternalLink,
  History, Compass, SlidersHorizontal
} from 'lucide-react';
import { fetchJsonCached } from '../lib/apiCache';
import { getDisplayTitle, getStoryPreviewText } from '../utils/textUtils';
import { proxyUrl } from '../lib/apiBase';

// Transliteration character mapping for Cyrillic/Latin script-agnostic matching
const SCRIPT_MAP: Record<string, string[]> = {
  'a': ['a', 'а', 'А', 'A'],
  'а': ['a', 'а', 'А', 'A'],
  'b': ['b', 'б', 'Б', 'B'],
  'б': ['b', 'б', 'Б', 'B'],
  'v': ['v', 'в', 'В', 'V'],
  'в': ['v', 'в', 'В', 'V'],
  'g': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'г': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'ѓ': ['g', 'г', 'Г', 'G', 'ѓ', 'Ѓ'],
  'd': ['d', 'д', 'Д', 'D'],
  'д': ['d', 'д', 'Д', 'D'],
  'đ': ['đ', 'ђ', 'Ђ', 'Đ'],
  'ђ': ['đ', 'ђ', 'Ђ', 'Đ'],
  'e': ['e', 'е', 'Е', 'E'],
  'е': ['e', 'е', 'Е', 'E'],
  'ž': ['ž', 'ж', 'Ж', 'Ž'],
  'ж': ['ž', 'ж', 'Ж', 'Ž'],
  'z': ['z', 'з', 'З', 'Z'],
  'з': ['z', 'з', 'З', 'Z'],
  'i': ['i', 'и', 'И', 'I'],
  'и': ['i', 'и', 'И', 'I'],
  'j': ['j', 'ј', 'Ј', 'J'],
  'ј': ['j', 'ј', 'Ј', 'J'],
  'k': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'к': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'ќ': ['k', 'к', 'К', 'K', 'ќ', 'Ќ'],
  'l': ['l', 'л', 'Л', 'L'],
  'л': ['l', 'л', 'Л', 'L'],
  'љ': ['љ', 'lj', 'Lj', 'LJ'],
  'm': ['m', 'м', 'М', 'M'],
  'м': ['m', 'м', 'М', 'M'],
  'n': ['n', 'н', 'Н', 'N'],
  'н': ['n', 'н', 'Н', 'N'],
  'њ': ['њ', 'nj', 'Nj', 'NJ'],
  'o': ['o', 'о', 'О', 'O'],
  'о': ['o', 'о', 'О', 'O'],
  'p': ['p', 'п', 'П', 'P'],
  'п': ['p', 'п', 'П', 'P'],
  'r': ['r', 'р', 'Р', 'R'],
  'р': ['r', 'р', 'Р', 'R'],
  's': ['s', 'с', 'С', 'S'],
  'с': ['s', 'с', 'С', 'S'],
  'ѕ': ['ѕ', 'dz', 'Dz', 'DZ'],
  't': ['t', 'т', 'Т', 'T'],
  'т': ['t', 'т', 'Т', 'T'],
  'ć': ['ć', 'ћ', 'Ћ', 'Ć'],
  'ћ': ['ć', 'ћ', 'Ћ', 'Ć'],
  'u': ['u', 'у', 'У', 'U'],
  'у': ['u', 'у', 'У', 'U'],
  'f': ['f', 'ф', 'Ф', 'F'],
  'ф': ['f', 'ф', 'Ф', 'F'],
  'h': ['h', 'х', 'Х', 'H'],
  'х': ['h', 'х', 'Х', 'H'],
  'c': ['c', 'ц', 'Ц', 'C'],
  'ц': ['c', 'ц', 'Ц', 'C'],
  'č': ['č', 'ч', 'Ч', 'Č'],
  'ч': ['č', 'ч', 'Ч', 'Č'],
  'џ': ['џ', 'dž', 'Dž', 'DŽ'],
  'š': ['š', 'ш', 'Ш', 'Š'],
  'ш': ['š', 'ш', 'Ш', 'Š']
};

function proxiedImage(url: string, width: number) {
  return proxyUrl(`/proxy?url=${encodeURIComponent(url)}&w=${width}`);
}

function getScriptAgnosticPattern(query: string) {
  let escaped = query.toLowerCase().replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
  
  // Replace digraphs first
  escaped = escaped.replace(/dž/g, '(џ|dž)');
  escaped = escaped.replace(/lj/g, '(љ|lj)');
  escaped = escaped.replace(/nj/g, '(њ|nj)');
  escaped = escaped.replace(/dz/g, '(ѕ|dz)');

  let result = '';
  for (let i = 0; i < escaped.length; i++) {
    const char = escaped[i];
    if (char === '(') {
      const endIdx = escaped.indexOf(')', i);
      if (endIdx !== -1) {
        result += escaped.substring(i, endIdx + 1);
        i = endIdx;
        continue;
      }
    }
    
    const mapping = SCRIPT_MAP[char];
    if (mapping) {
      result += `[${Array.from(new Set(mapping)).join('')}]`;
    } else {
      result += char;
    }
  }
  return result;
}

// Helper function to highlight matching search query text (script-agnostic)
function highlightMatch(text: string, query: string) {
  if (!query.trim()) return text;
  const pattern = getScriptAgnosticPattern(query);
  const regex = new RegExp(`(${pattern})`, 'gi');
  const testRegex = new RegExp(`^(${pattern})$`, 'i');
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        testRegex.test(part) ? (
          <mark key={i} className="bg-amber-500/20 text-amber-900 dark:bg-amber-500/30 dark:text-amber-300 font-bold px-0.5 rounded-none">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
}

function SearchSkeleton({ lang = 'sr' }: { lang?: string }) {
  return (
    <div className="space-y-6 animate-pulse">
      <section>
        <div className="h-3 w-32 bg-muted-foreground/20 rounded-none mb-4" />
        <div className="space-y-2.5">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex items-start gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-none border border-border/10 bg-secondary/15">
              <div className="w-14 sm:w-16 aspect-[4/3] rounded-none bg-muted-foreground/15 shrink-0" />
              <div className="flex-1 min-w-0 space-y-2">
                <div className="h-2.5 w-16 bg-muted-foreground/15 rounded-none" />
                <div className="h-3.5 w-5/6 bg-muted-foreground/15 rounded-none" />
                <div className="h-2.5 w-2/3 bg-muted-foreground/15 rounded-none" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
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

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export default function SearchIsland({
  initialQuery = '',
  lang = 'sr',
  startOpen = false,
  hideTrigger = false,
  onClose,
}: {
  initialQuery?: string | null;
  lang?: Locale;
  startOpen?: boolean;
  hideTrigger?: boolean;
  onClose?: () => void;
}) {
  const t = useClientTranslations(lang, search, news, common);
  const [isOpen, setIsOpen] = useState(startOpen);
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
  const recognitionRef = useRef<any>(null);
  const openSearch = useCallback(() => setIsOpen(true), []);

  const closeSearch = useCallback(() => {
    setIsOpen(false);
    if (onClose) {
      onClose();
      return;
    }
    window.setTimeout(() => {
      if (lastFocusedRef.current && document.contains(lastFocusedRef.current)) {
        lastFocusedRef.current.focus();
      } else {
        triggerRef.current?.focus();
      }
    }, 0);
  }, [onClose]);

  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  const SEARCH_ACTIONS: SearchAction[] = [
    { id: 'act-briefing', label: t('search.action_briefing_label'), icon: Zap, href: localePathForLang('/briefing', lang), category: 'NAVIGATION', desc: t('search.action_briefing_desc') },
    { id: 'act-foryou', label: t('search.action_foryou_label'), icon: Compass, href: localePathForLang('/for-you', lang), category: 'NAVIGATION', desc: t('search.action_foryou_desc') },
    { id: 'act-pulse', label: t('search.action_pulse_label'), icon: Activity, href: localePathForLang('/pulse', lang), category: 'NAVIGATION', desc: t('search.action_pulse_desc') },
    { id: 'act-archive', label: t('search.action_archive_label'), icon: Archive, href: localePathForLang('/archive', lang), category: 'NAVIGATION', desc: t('search.action_archive_desc') },
  ];

  const CATEGORIES = [
    { id: 'all', label: t('search.category_all'), color: 'bg-foreground' },
    { id: t('search.category_country_value'), label: t('search.category_country'), color: 'bg-nyt-red' },
    { id: 'Politika', label: t('search.category_politika'), color: 'bg-blue-600' },
    { id: 'Ekonomija', label: t('search.category_ekonomija'), color: 'bg-emerald-600' },
    { id: 'Sport', label: t('search.category_sport'), color: 'bg-orange-500' },
    { id: 'Kultura', label: t('search.category_kultura'), color: 'bg-purple-600' },
    { id: 'Tehnologija', label: t('search.category_tehnologija'), color: 'bg-cyan-600' },
  ];

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
      if (hideTrigger) {
        if (e.key === 'Escape' && isOpen) closeSearch();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openSearch();
        return;
      }
      if (e.key === '/' && !isOpen && !isEditableTarget(e.target)) {
        e.preventDefault();
        openSearch();
        return;
      }
      if (e.key === 'Escape') closeSearch();
    };

    const handleOpenEvent = () => openSearch();

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('presek:open-search', handleOpenEvent);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('presek:open-search', handleOpenEvent);
    };
  }, [isOpen, openSearch, closeSearch, hideTrigger]);

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

  // Focus Trapping Effect
  useEffect(() => {
    if (!isOpen) return;
    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      if (!dialogRef.current) return;
      const focusableElements = dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR);
      if (focusableElements.length === 0) return;
      
      const firstElement = focusableElements[0] as HTMLElement;
      const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;
      
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          lastElement.focus();
          e.preventDefault();
        }
      } else {
        if (document.activeElement === lastElement) {
          firstElement.focus();
          e.preventDefault();
        }
      }
    };
    window.addEventListener('keydown', handleTabKey);
    return () => window.removeEventListener('keydown', handleTabKey);
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
          setTrendingItems(data.filter((item) => typeof item?.word === 'string').slice(0, 10));
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
        const data = await fetchJsonCached(url + timespanPart + categoryPart, 120_000);
        const nextSuggestions = Array.isArray(data?.clusters)
          ? data.clusters.map((cluster: any) => {
              const article = cluster.articles?.[0] || {};
              const syntheticTitle = String(cluster.synthetic_headline || '').trim();
              const title = syntheticTitle
                ? getDisplayTitle({ title: syntheticTitle }, t('search.title_fallback'), lang)
                : getDisplayTitle(article, t('search.title_fallback'), lang);
              const description = getStoryPreviewText(cluster, article, lang);
              return {
                cluster_id: cluster.cluster_id,
                title,
                image_url: cluster.representative_image || article.image_url || null,
                source: article.source || '',
                category: article.category || '',
                description,
                sourceCount: cluster.articles?.length || 0,
                pulse_score: cluster.pulse_score,
                has_synthesis: cluster.has_synthesis,
                matchLabel: cluster.is_breaking ? t('search.match_urgent') : t('search.match_story'),
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
          setError(err instanceof Error ? err.message : t('search.error'));
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 200);

    return () => {
      cancelled = true;
      if (typeof window !== 'undefined') window.clearTimeout(timer);
    };
  }, [query, isOpen, timespan, categoryFilter, lang, t]);

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
    navigate(`${localePathForLang('/', lang)}?q=${encodeURIComponent(cleanQuery)}${tsPart}${catPart}`);
  };

  const navigateToCluster = (clusterId: string) => {
    if (!clusterId) return;
    closeSearch();
    navigate(`${localePathForLang(`/cluster/${clusterId}`, lang)}`);
  };

  const onDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const resultCount = suggestions.length + (entityResult ? 1 : 0) + filteredActions.length;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev < 0 ? 0 : (prev + 1) % resultCount));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? -1 : prev - 1));
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
      className="fixed inset-0 z-[10000] bg-background/80 backdrop-blur-3xl flex items-center justify-center transition-all animate-in fade-in duration-300 search-overlay-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t('search.dialog_label')}
      onKeyDown={onDialogKeyDown}
      onClick={closeSearch}
    >
      <div
        ref={dialogRef}
        className="search-page-scope w-full max-w-6xl h-[100dvh] sm:h-[92vh] md:h-[80vh] bg-card/85 backdrop-blur-xl border-x border-border/50 sm:border sm:border-border/50 shadow-premium sm:rounded-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 mx-0 sm:mx-4"
        data-page-scope="search"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Command Header */}
        <div className="flex items-center gap-3 px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/10">
          <Search className="hidden sm:block text-muted-foreground" size={24} />
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              data-testid="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('search.input_placeholder')}
              className="w-full bg-transparent py-2.5 sm:py-4 text-xl sm:text-2xl md:text-3xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 border-b-2 border-transparent focus:border-foreground transition-colors search-cmd-input"
              autoComplete="off"
              spellCheck="false"
            />
            {isLoading && (
              <div className="absolute right-0 top-1/2 -translate-y-1/2">
                <LoaderCircle size={20} className="animate-spin text-muted-foreground" />
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 sm:gap-[var(--grid-gap)]">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`search-cmd-toolbar-btn p-2 hover:bg-secondary transition-colors ${showFilters ? 'text-muted-foreground' : 'text-muted-foreground'}`}
              title={t('search.filters_title')}
            >
              <SlidersHorizontal size={18} />
            </button>
            <button onClick={startVoiceSearch} className={`search-cmd-toolbar-btn p-2 rounded-none hover:bg-secondary transition-colors ${isListening ? 'text-muted-foreground animate-pulse' : 'text-muted-foreground'}`}>
              <Mic size={18} />
            </button>
            <button onClick={closeSearch} className="search-cmd-toolbar-btn p-2 rounded-none hover:bg-secondary text-muted-foreground transition-colors">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Voice Search listening overlay */}
        {isListening && (
          <div className="absolute inset-0 bg-background/95 backdrop-blur-md z-[10001] flex flex-col items-center justify-center gap-6 animate-in fade-in duration-300">
            <div className="w-20 h-20 bg-secondary rounded-full flex items-center justify-center text-muted-foreground animate-pulse border border-border shadow-lg">
              <Mic size={36} />
            </div>
            
            <div className="flex items-center gap-1.5 h-10 justify-center">
              {[...Array(6)].map((_, i) => (
                <div
                  key={i}
                  className="w-1.5 bg-foreground rounded-full animate-bounce"
                  style={{
                    height: '24px',
                    animationDelay: `${i * 0.15}s`,
                    animationDuration: '0.8s'
                  }}
                />
              ))}
            </div>
            
            <p className="font-serif font-black text-xl text-center">
              {t('search.listening')}
            </p>
            
            <button
              onClick={stopVoiceSearch}
              className="search-cmd-cta px-6 py-2.5 bg-secondary hover:bg-secondary-foreground/10 border border-border rounded-none transition-all"
            >
              {t('search.cancel')}
            </button>
          </div>
        )}

        {/* Filters Collapsible Panel */}
        {showFilters && (
          <div className="px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/15 flex flex-col md:flex-row gap-4 md:items-center animate-in slide-in-from-top-4 duration-300">
            {/* Category Filter */}
            <div className="flex-1">
              <span className="ui-kicker text-muted-foreground block mb-2">
                {t('search.topic_label')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setCategoryFilter(cat.id)}
                    className={`search-cmd-chip px-3 py-1 rounded-none transition-all border ${
                      categoryFilter === cat.id
                        ? 'bg-foreground text-background border-foreground shadow-sm'
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
              <span className="ui-kicker text-muted-foreground block mb-2">
                {t('search.timespan_label')}
              </span>
              <div className="flex gap-1.5">
                {[
                  { id: 'all', label: t('search.timespan_all') },
                  { id: '24h', label: t('search.timespan_24h') },
                  { id: '7d', label: t('search.timespan_7d') },
                  { id: '30d', label: t('search.timespan_30d') },
                ].map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setTimespan(option.id)}
                    className={`search-cmd-chip px-3 py-1 rounded-none transition-all border ${
                      timespan === option.id
                        ? 'bg-foreground text-background border-foreground shadow-sm'
                        : 'bg-background hover:bg-secondary border-border text-foreground'
                    }`}
                  >
                    {option.label}
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
                    <h3 className="ui-kicker mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                       <History size={12} /> {t('search.recent_searches')}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {recentSearches.map((s, i) => (
                        <div
                          key={i}
                          onClick={() => setQuery(s.query)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary/50 hover:bg-secondary border border-border/50 rounded-none text-[11px] sm:text-xs font-bold transition-all cursor-pointer group/pill"
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
                            title={t('search.remove_search')}
                          >
                            <X size={10} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                <section>
                  <h3 className="ui-kicker mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                     <TrendingUp size={12} /> {t('search.trending_topics')}
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2 sm:gap-[var(--grid-gap)]">
                    {trendingItems.length > 0 ? trendingItems.map((item, i) => (
                      <button key={i} onClick={() => setQuery(item.word)} className="flex items-center gap-2 sm:gap-[var(--grid-gap)] p-2.5 sm:p-3 bg-secondary/30 hover:bg-secondary/60 rounded-none transition-all group text-left">
                        <span className="ui-label-min text-muted-foreground/50 group-hover:text-foreground">{(i+1).toString().padStart(2, '0')}</span>
                        <span className="font-serif font-black text-[13px] sm:text-sm truncate">{item.word}</span>
                      </button>
                    )) : [1,2,3,4,5,6].map(i => <div key={i} className="h-12 bg-secondary/20 animate-pulse rounded-none"></div>)}
                  </div>
                </section>

                <section>
                  <h3 className="ui-kicker mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
                     <Zap size={12} /> {t('search.quick_actions')}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-[var(--grid-gap)]">
                    {SEARCH_ACTIONS.map(action => (
                      <button key={action.id} onClick={() => { closeSearch(); navigate(action.href); }} className="flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 bg-secondary/30 hover:bg-secondary/60 border border-border/50 rounded-none transition-all group text-left">
                        <div className="p-2 bg-background rounded-none text-muted-foreground group-hover:text-foreground group-hover:bg-secondary transition-all">
                          <action.icon size={18} />
                        </div>
                        <div>
                          <p className="search-cmd-action-title">{action.label}</p>
                          <p className="ui-label-min text-muted-foreground line-clamp-1">{action.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* One-character hint */}
            {query.trim().length === 1 && (
              <div className="py-10 sm:py-14 flex flex-col items-center text-center text-muted-foreground">
                <Search size={28} className="mb-4 opacity-30" />
                <p className="text-sm sm:text-base max-w-sm">{t('search.type_more')}</p>
              </div>
            )}

            {/* Results List */}
            {query.trim().length >= 2 && (
              <div className="space-y-6 sm:space-y-8">
                {!isLoading && (
                  <button
                    type="button"
                    onClick={() => navigateToQuery(query)}
                    className={`w-full flex items-center gap-3 p-3 sm:p-4 rounded-none border transition-all text-left ${
                      activeIndex === -1
                        ? 'bg-secondary/80 border-border ring-1 ring-border'
                        : 'bg-secondary/20 border-border/50 hover:bg-secondary/40'
                    }`}
                  >
                    <Search size={18} className="text-muted-foreground shrink-0" />
                    <span className="search-cmd-action-title text-foreground">
                      {t('search.search_all', { query: query.trim() })}
                    </span>
                    <ArrowUpRight size={16} className="ml-auto text-muted-foreground shrink-0" />
                  </button>
                )}

                {isLoading ? (
                  <SearchSkeleton lang={lang} />
                ) : (
                  <>
                    {entityResult && (
                      <section>
                        <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.subjects')}</h3>
                        <button
                          onClick={() => navigateToQuery(entityResult.name)}
                          className={`w-full flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-none border transition-all text-left ${activeIndex === 0 ? 'bg-secondary/80 border-border ring-1 ring-border' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                        >
                          <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-none overflow-hidden bg-secondary flex items-center justify-center shrink-0 border border-border">
                            {entityResult.image_url ? (
                              <img src={proxiedImage(entityResult.image_url, 128)} className="w-full h-full object-cover" />
                            ) : (
                              <User size={24} className="text-muted-foreground" />
                            )}
                          </div>
                          <div>
                            <p className="font-serif font-black text-lg sm:text-xl">{highlightMatch(entityResult.name, query)}</p>
                            <p className="ui-label-min text-muted-foreground">{entityResult.type} · {entityResult.total_mentions} {t('search.mentions')}</p>
                          </div>
                          <ArrowUpRight size={16} className="ml-auto text-muted-foreground" />
                        </button>
                      </section>
                    )}

                    {suggestions.length > 0 && (
                      <section>
                        <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.stories')}</h3>
                        <div className="space-y-2">
                          {suggestions.map((item, idx) => {
                            const globalIdx = entityResult ? idx + 1 : idx;
                            return (
                              <button
                                key={item.cluster_id}
                                onClick={() => navigateToCluster(item.cluster_id)}
                                className={`w-full flex items-start gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-none border transition-all text-left group ${
                                  item.has_synthesis
                                    ? 'bg-amber-500/5 border-amber-500/10 hover:border-amber-500/30'
                                    : 'bg-transparent border-transparent hover:bg-secondary/30'
                                } ${activeIndex === globalIdx ? 'bg-secondary/80 border-border ring-1 ring-border' : ''}`}
                              >
                                <div className="w-14 sm:w-16 aspect-[4/3] rounded-none overflow-hidden bg-secondary shrink-0 border border-border/50">
                                  {item.image_url && <img src={proxiedImage(item.image_url, 200)} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-1.5 mb-1">
                                    <span className={`ui-label-min ${item.has_synthesis ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}`}>{item.category}</span>
                                    {item.has_synthesis && (
                                      <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-none bg-amber-500/10 text-amber-600 dark:text-amber-400 ui-label-min">
                                        <Sparkles size={8} fill="currentColor" />
                                        {t('search.synthesis')}
                                      </span>
                                    )}
                                  </div>
                                  <p className="font-serif font-black text-base sm:text-lg leading-tight line-clamp-2 group-hover:text-foreground transition-colors">{highlightMatch(item.title, query)}</p>
                                  {item.description && (
                                    <p className="mt-1 text-[12px] sm:text-[13px] text-muted-foreground line-clamp-2 leading-snug">{highlightMatch(item.description, query)}</p>
                                  )}
                                  <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)] mt-1.5 sm:mt-2 ui-label-min text-muted-foreground/60">
                                    <span>{item.source}</span>
                                    <span>{item.sourceCount} {item.sourceCount === 1 ? t('news.source') : t('news.sources')}</span>
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </section>
                    )}
                  </>
                )}


                {filteredActions.length > 0 && (
                  <section>
                    <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.actions')}</h3>
                    <div className="grid grid-cols-1 gap-[var(--grid-gap)]">
                      {filteredActions.map((action, idx) => {
                        const globalIdx = (entityResult ? 1 : 0) + suggestions.length + idx;
                        return (
                          <button
                            key={action.id}
                            onClick={() => { closeSearch(); navigate(action.href); }}
                            className={`w-full flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 rounded-none border transition-all text-left ${activeIndex === globalIdx ? 'bg-secondary/80 border-border ring-1 ring-border' : 'bg-transparent border-transparent hover:bg-secondary/30'}`}
                          >
                            <div className="p-2 bg-secondary rounded-none text-muted-foreground">
                              <action.icon size={16} />
                            </div>
                            <span className="search-cmd-action-title">{action.label}</span>
                            <span className="hidden sm:inline ui-label-min text-muted-foreground opacity-60">→ {action.href}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                )}

                {!isLoading && suggestions.length === 0 && !entityResult && filteredActions.length === 0 && (
                  <div className="py-14 sm:py-20 flex flex-col items-center text-center">
                    <div className="w-14 h-14 sm:w-16 sm:h-16 bg-secondary/50 rounded-none flex items-center justify-center mb-5 sm:mb-6">
                       <Search size={32} className="text-muted-foreground/30" />
                    </div>
                    <h4 className="font-serif font-black text-xl sm:text-2xl mb-2">{t('search.no_results_title', { query })}</h4>
                    <p className="text-muted-foreground text-[13px] sm:text-sm max-w-xs">{t('search.no_results_desc')}</p>
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
                    <div className="aspect-[16/9] rounded-none overflow-hidden bg-secondary border border-border shadow-sm">
                      {selectedItem.data.image_url && <img src={proxiedImage(selectedItem.data.image_url, 600)} className="w-full h-full object-cover" />}
                    </div>

                    <div>
                      <div className="flex items-center gap-2 mb-3">
                         <span className="px-2 py-1 bg-foreground text-background search-cmd-preview-badge rounded">{selectedItem.data.category}</span>
                         {selectedItem.data.has_synthesis && (
                           <span className="px-2 py-1 bg-gradient-to-r from-amber-500 to-amber-600 text-white search-cmd-preview-badge rounded flex items-center gap-1 shadow-sm shadow-amber-500/20">
                             <Sparkles size={10} fill="currentColor" />
                             {t('search.synthesis')}
                           </span>
                         )}
                         <span className="ui-kicker text-muted-foreground flex items-center gap-1"><Clock size={12} /> {t('search.preview_hours_ago')}</span>
                      </div>
                      <h2 className="font-serif font-black text-2xl leading-tight mb-4">{selectedItem.data.title}</h2>
                      <p className="text-base text-muted-foreground leading-relaxed font-nyt-body line-clamp-6">{selectedItem.data.description}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-[var(--grid-gap)] py-6 border-y border-border/40">
                      <div>
                        <p className="ui-kicker text-muted-foreground mb-1">{t('search.sources_label')}</p>
                        <p className="text-xl font-black">{selectedItem.data.sourceCount}</p>
                      </div>
                      <div>
                        <p className="ui-kicker text-muted-foreground mb-1">{t('search.score_label')}</p>
                        <p className="text-xl font-black text-muted-foreground">{selectedItem.data.pulse_score || '8.2'}</p>
                      </div>
                    </div>

                    <button
                      onClick={() => navigateToCluster(selectedItem.data.cluster_id)}
                      className="search-cmd-cta w-full py-4 bg-foreground text-background rounded-none shadow-lg hover:scale-[1.02] transition-all flex items-center justify-center gap-[var(--grid-gap)]"
                    >
                      {t('search.open_story')} <ChevronRight size={16} />
                    </button>
                  </div>
                )}

                {selectedItem.type === 'ENTITY' && (
                  <div className="space-y-8">
                    <div className="flex flex-col items-center text-center">
                      <div className="w-32 h-32 rounded-full overflow-hidden border-4 border-border mb-6 bg-secondary flex items-center justify-center">
                        {selectedItem.data.image_url ? (
                          <img src={proxiedImage(selectedItem.data.image_url, 256)} className="w-full h-full object-cover" />
                        ) : (
                          <User size={64} className="text-muted-foreground/40" />
                        )}
                      </div>
                      <h2 className="font-serif font-black text-3xl mb-2">{selectedItem.data.name}</h2>
                      <p className="px-4 py-1.5 bg-secondary border border-border rounded-none ui-label-min text-muted-foreground">{selectedItem.data.type}</p>
                    </div>

                    <div className="space-y-4">
                       <div className="p-4 bg-background border border-border rounded-none">
                          <p className="ui-kicker text-muted-foreground mb-4">{t('search.media_presence')}</p>
                          <div className="flex items-end gap-1 h-12 mb-2">
                            {[30, 50, 40, 80, 60, 90, 75, 85].map((h, i) => (
                              <div key={i} className="flex-1 bg-muted rounded-t-sm group relative" style={{ height: `${h}%` }}>
                                <div className="absolute inset-0 bg-foreground opacity-0 group-hover:opacity-100 transition-opacity rounded-t-sm" />
                              </div>
                            ))}
                          </div>
                          <p className="text-xs font-bold">{selectedItem.data.total_mentions} {t('search.mentions_in_archive')}</p>
                       </div>

                       <div className="p-4 bg-background border border-border rounded-none flex items-center justify-between">
                          <div>
                            <p className="ui-kicker text-muted-foreground mb-1">{t('search.sentiment_label')}</p>
                            <p className="font-serif font-black text-lg text-emerald-600">{t('search.sentiment_positive')}</p>
                          </div>
                          <Activity size={24} className="text-emerald-500" />
                       </div>
                    </div>

                    <button
                      onClick={() => navigateToQuery(selectedItem.data.name)}
                      className="search-cmd-cta w-full py-4 bg-foreground text-background rounded-none hover:opacity-90 transition-all flex items-center justify-center gap-[var(--grid-gap)]"
                    >
                      {t('search.view_all_stories')} <ExternalLink size={16} />
                    </button>
                  </div>
                )}

                {selectedItem.type === 'ACTION' && (
                  <div className="h-full flex flex-col justify-center items-center text-center space-y-6">
                    <div className="w-24 h-24 bg-secondary rounded-none flex items-center justify-center text-muted-foreground rotate-3">
                       <selectedItem.data.icon size={48} />
                    </div>
                    <div>
                      <h2 className="font-serif font-black text-3xl mb-2">{selectedItem.data.label}</h2>
                      <p className="text-muted-foreground text-sm max-w-[280px] leading-relaxed">{selectedItem.data.desc}</p>
                    </div>
                    <button
                      onClick={() => { closeSearch(); navigate(selectedItem.data.href); }}
                      className="search-cmd-cta px-10 py-4 bg-foreground text-background rounded-none hover:opacity-90 transition-all"
                    >
                      {t('search.open')}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-30 select-none">
                <div className="w-20 h-20 border-2 border-dashed border-muted-foreground rounded-full flex items-center justify-center mb-6">
                   <Layout size={32} />
                </div>
                <p className="font-serif font-black text-xl mb-1">{t('search.preview_title')}</p>
                <p className="ui-label-min">{t('search.preview_hint')}</p>
              </div>
            )}
          </div>
        </div>

        {/* Command Footer */}
        <div className="px-4 sm:px-6 py-2.5 sm:py-3 border-t border-border/40 bg-secondary/5 flex items-center justify-between search-cmd-footer-hint gap-3">
           <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] sm:text-[11px]">
              <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 bg-background border border-border rounded-none">Enter</kbd> {t('search.shortcut_select')}</span>
              <span className="hidden sm:flex items-center gap-1"><kbd className="px-1 py-0.5 bg-background border border-border rounded-none">↑</kbd><kbd className="px-1 py-0.5 bg-background border border-border rounded-none">↓</kbd> {t('search.shortcut_nav')}</span>
              <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 bg-background border border-border rounded-none">Esc</kbd> {t('search.shortcut_close')}</span>
           </div>
           <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)]">
              <span className="flex items-center gap-1.5"><Globe size={12} /> {t('search.global_search')}</span>
              <span className="hidden sm:inline w-1 h-1 rounded-full bg-border" />
              <span className="hidden sm:flex items-center gap-1.5"><Sparkles size={12} /> {t('search.smart_assist')}</span>
           </div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {!hideTrigger && (
      <button
        ref={triggerRef}
        type="button"
        onClick={openSearch}
        data-testid="search-trigger"
        className="presek-search-trigger group"
        aria-label={t('search.open_search')}
        aria-keyshortcuts="Meta+K /"
      >
        <span className="search-trigger-icon" aria-hidden="true">
          <Search size={16} strokeWidth={2.25} />
        </span>
        <span className="search-trigger-copy">
          <span className="search-trigger-label">{t('header.search_placeholder')}</span>
          <span className="search-trigger-hint">
            {t('search.hint_topics')}
          </span>
        </span>
        <span className="search-trigger-shortcuts" aria-hidden="true">
          <kbd className="search-trigger-kbd search-trigger-kbd--slash">/</kbd>
          <kbd className="search-trigger-kbd search-trigger-kbd--meta">
            <span className="search-trigger-kbd-meta">⌘</span>K
          </kbd>
        </span>
      </button>
      )}

      {typeof document !== 'undefined' ? createPortal(overlayContent, document.body) : null}
    </>
  );
}
