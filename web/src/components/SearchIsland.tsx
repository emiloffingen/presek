import { localePathForLang, type Locale } from '../lib/localePaths';
import { useClientTranslations } from '../i18n/clientTranslations';
import { search } from '../i18n/namespaces/search';
import { news } from '../i18n/namespaces/news';
import { common } from '../i18n/namespaces/common';
import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { navigate } from 'astro:transitions/client';
import {
  Search,
  X,
  Zap,
  Mic,
  SlidersHorizontal,
  Compass,
  Activity,
  Archive,
} from 'lucide-react';

import { fetchJson } from '../lib/apiCache';
import { getDisplayTitle, getStoryPreviewText } from '../utils/textUtils';
import { SearchInput } from './search/SearchInput';
import { SearchFilters } from './search/SearchFilters';
import { SearchResults } from './search/SearchResults';
import { SearchPreview } from './search/SearchPreview';
import { SearchFooter } from './search/SearchFooter';
import { VoiceSearchOverlay } from './search/VoiceSearchOverlay';
import { useSearchSession, loadSearchSession } from './search/useSearchSession';
import {
  type Suggestion,
  type EntityResult,
  type TrendingItem,
  type SearchAction,
  type CategoryOption,
  type TimespanOption,
  type RecentSearch,
  type SelectedItem,
  type SearchIslandProps,
  type SearchApiResponse,
  type SpeechRecognition,
  isEntityResult,
  isTrendingItem,
  isRecentSearch,
} from './search/types';

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
const RECENT_SEARCHES_KEY = 'presek_recent_searches';

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

function isSpeechRecognitionSupported(): boolean {
  return typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export default function SearchIsland({
  initialQuery = '',
  lang = 'sr',
  startOpen = false,
  hideTrigger = false,
  onClose,
}: SearchIslandProps) {
  const t = useClientTranslations(lang, search, news, common);
  const [isOpen, setIsOpen] = useState(startOpen);
  const [query, setQuery] = useState(initialQuery || '');
  const [timespan, setTimespan] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [recentSearches, setRecentSearches] = useState<RecentSearch[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [entityResult, setEntityResult] = useState<EntityResult | null>(null);
  const [trendingItems, setTrendingItems] = useState<TrendingItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchTime, setSearchTime] = useState<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isListening, setIsListening] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClearRecentSearches = useCallback(() => {
    setRecentSearches([]);
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(RECENT_SEARCHES_KEY);
      } catch (e) {}
    }
  }, []);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const queryCacheRef = useRef<Record<string, { suggestions: Suggestion[]; entity: EntityResult | null }>>({});
  const queryRef = useRef(query);
  queryRef.current = query;

  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const navRefs = useRef<Map<number, HTMLElement>>(new Map());

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

  // Memoize translation-derived constants by lang only; the t() identity changes
  // every render but its output is fully determined by lang.
  const SEARCH_ACTIONS: SearchAction[] = useMemo(
    () => [
      {
        id: 'act-briefing',
        label: t('search.action_briefing_label'),
        icon: Zap,
        href: localePathForLang('/briefing', lang),
        category: 'NAVIGATION',
        desc: t('search.action_briefing_desc'),
      },
      {
        id: 'act-foryou',
        label: t('search.action_foryou_label'),
        icon: Compass,
        href: localePathForLang('/for-you', lang),
        category: 'NAVIGATION',
        desc: t('search.action_foryou_desc'),
      },
      {
        id: 'act-pulse',
        label: t('search.action_pulse_label'),
        icon: Activity,
        href: localePathForLang('/pulse', lang),
        category: 'NAVIGATION',
        desc: t('search.action_pulse_desc'),
      },
      {
        id: 'act-archive',
        label: t('search.action_archive_label'),
        icon: Archive,
        href: localePathForLang('/archive', lang),
        category: 'NAVIGATION',
        desc: t('search.action_archive_desc'),
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps
    ],
    [lang]
  );

  const CATEGORIES: CategoryOption[] = useMemo(
    () => [
      { id: 'all', labelKey: 'search.category_all', apiValue: '', color: 'bg-foreground' },
      { id: 'country', labelKey: 'search.category_country', apiValue: t('search.category_country_value'), color: 'bg-nyt-red' },
      { id: 'politics', labelKey: 'search.category_politika', apiValue: 'Politika', color: 'bg-blue-600' },
      { id: 'economy', labelKey: 'search.category_ekonomija', apiValue: 'Ekonomija', color: 'bg-emerald-600' },
      { id: 'sports', labelKey: 'search.category_sport', apiValue: 'Sport', color: 'bg-orange-500' },
      { id: 'culture', labelKey: 'search.category_kultura', apiValue: 'Kultura', color: 'bg-purple-600' },
      { id: 'technology', labelKey: 'search.category_tehnologija', apiValue: 'Tehnologija', color: 'bg-cyan-600' },
      // eslint-disable-next-line react-hooks/exhaustive-deps
    ],
    [lang]
  );

  const TIMESPANS: TimespanOption[] = useMemo(
    () => [
      { id: 'all', labelKey: 'search.timespan_all' },
      { id: '24h', labelKey: 'search.timespan_24h' },
      { id: '7d', labelKey: 'search.timespan_7d' },
      { id: '30d', labelKey: 'search.timespan_30d' },
    ],
    []
  );

  const activeCategory = useMemo(
    () => CATEGORIES.find((c) => c.id === categoryFilter) || CATEGORIES[0],
    [CATEGORIES, categoryFilter]
  );

  useSearchSession({ query, timespan, categoryFilter, isOpen });

  useEffect(() => {
    if (initialQuery !== undefined && initialQuery !== null && query !== initialQuery) {
      setQuery(initialQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let saved = null;
    try {
      saved = localStorage.getItem(RECENT_SEARCHES_KEY);
    } catch (e) {
      console.warn('localStorage not accessible:', e);
    }
    if (saved) {
      try {
        const parsed: unknown = JSON.parse(saved);
        let loaded: RecentSearch[] = [];
        if (Array.isArray(parsed)) {
          if (parsed.length > 0 && parsed.every((q): q is string => typeof q === 'string')) {
            loaded = parsed.map((q) => ({ query: q, timestamp: Date.now() }));
          } else {
            loaded = parsed.filter(isRecentSearch);
          }
        }
        setRecentSearches(loaded.slice(0, 5));
      } catch {
        setRecentSearches([]);
      }
    }

    // Restore search session state from sessionStorage
    const sessionState = loadSearchSession();
    if (sessionState) {
      if (sessionState.query) setQuery(sessionState.query);
      if (sessionState.timespan) setTimespan(sessionState.timespan);
      if (sessionState.categoryFilter) setCategoryFilter(sessionState.categoryFilter);
      if (sessionState.isOpen) setIsOpen(true);
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

      // Numerical hotkeys for Quick Actions when search query is empty
      if (isOpen && !queryRef.current.trim()) {
        const keyNum = parseInt(e.key, 10);
        if (keyNum >= 1 && keyNum <= 4) {
          const action = SEARCH_ACTIONS[keyNum - 1];
          if (action) {
            e.preventDefault();
            closeSearch();
            navigate(action.href);
            return;
          }
        }
      }
    };

    const handleOpenEvent = () => openSearch();

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('presek:open-search', handleOpenEvent);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('presek:open-search', handleOpenEvent);
    };
  }, [isOpen, openSearch, closeSearch, hideTrigger, lang, SEARCH_ACTIONS]);

  const startVoiceSearch = useCallback(() => {
    if (!isSpeechRecognitionSupported()) return;

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    const recognition = new SpeechRecognitionCtor();
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
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setQuery(transcript);
        setIsListening(false);
      }
    };
    recognition.start();
  }, [lang]);

  const stopVoiceSearch = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (e) {
        console.error(e);
      }
    }
    setIsListening(false);
  }, []);

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
        const data: unknown = await res.json();
        if (!cancelled && Array.isArray(data)) {
          setTrendingItems(data.filter(isTrendingItem).slice(0, 10));
        }
      } catch {
        if (!cancelled) setTrendingItems([]);
      }
    };
    loadTrending();
    return () => {
      cancelled = true;
    };
  }, [isOpen, lang]);

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setSearchTime(null);
      setIsLoading(false);
      setActiveIndex(-1);
      return;
    }

    const timespanPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
    const categoryApiValue = activeCategory.apiValue;
    const categoryPart = categoryFilter !== 'all' && categoryApiValue ? `&category=${encodeURIComponent(categoryApiValue)}` : '';
    const cacheKey = trimmed + timespanPart + categoryPart;

    // Check synchronous query cache first for instant feedback (e.g. backspace / switching filters)
    if (queryCacheRef.current[cacheKey]) {
      const cached = queryCacheRef.current[cacheKey];
      setSuggestions(cached.suggestions);
      setEntityResult(cached.entity);
      setSearchTime(1);
      setIsLoading(false);
      setActiveIndex(-1);
      return;
    }

    let cancelled = false;
    const aborter = new AbortController();
    const startTime = performance.now();
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const url = `/api/news?q=${encodeURIComponent(trimmed)}&page_size=12&lang=${lang}`;
        // Direct (non-promise-cached) fetch: each keystroke is a unique URL and the
        // per-query sync cache above already covers repeats. Abortable so typing
        // cancels superseded backend searches instead of queueing them.
        const data = (await fetchJson(url + timespanPart + categoryPart, 2, {
          signal: aborter.signal,
        })) as SearchApiResponse;
        const nextSuggestions = Array.isArray(data.clusters)
          ? data.clusters.map((cluster: unknown) => {
              const clusterRecord = cluster as Record<string, unknown>;
              const articles = Array.isArray(clusterRecord.articles) ? clusterRecord.articles : [];
              const article = (articles[0] as Record<string, unknown>) || {};
              const syntheticTitle = String(clusterRecord.synthetic_headline || '').trim();
              const title = syntheticTitle
                ? getDisplayTitle({ title: syntheticTitle }, t('search.title_fallback'), lang)
                : getDisplayTitle(article, t('search.title_fallback'), lang);
              const description = getStoryPreviewText(clusterRecord, article, lang);
              return {
                cluster_id: String(clusterRecord.cluster_id),
                title,
                image_url: String(clusterRecord.representative_image || article.image_url || ''),
                source: String(article.source || ''),
                category: String(article.category || ''),
                description,
                sourceCount: Array.isArray(clusterRecord.articles) ? clusterRecord.articles.length : 0,
                pulse_score: typeof clusterRecord.pulse_score === 'number' ? clusterRecord.pulse_score : undefined,
                has_synthesis: Boolean(clusterRecord.has_synthesis),
                matchLabel: clusterRecord.is_breaking ? t('search.match_urgent') : t('search.match_story'),
              };
            })
          : [];

        if (!cancelled) {
          const entity = isEntityResult(data.entity) ? data.entity : null;
          const duration = Math.round(performance.now() - startTime);
          setSearchTime(duration);
          // Save in cache
          queryCacheRef.current[cacheKey] = { suggestions: nextSuggestions, entity };
          setSuggestions(nextSuggestions);
          setEntityResult(entity);
          setActiveIndex(-1);
        }
      } catch (err) {
        // Aborted by newer keystrokes: stay silent, a fresher request is in flight.
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (!cancelled) {
          setSuggestions([]);
          setEntityResult(null);
          setSearchTime(null);
          setError(err instanceof Error ? err.message : t('search.error'));
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, 280); // Debounced to avoid firing a ~1.5s backend search on every keystroke

    return () => {
      cancelled = true;
      aborter.abort();
      if (typeof window !== 'undefined') window.clearTimeout(timer);
    };
  }, [query, isOpen, timespan, categoryFilter, lang, t, activeCategory]);

  // Auto-scroll highlighted keyboard navigation element into view. Skip the
  // default "search all" selection (activeIndex === -1) to avoid smooth-scroll
  // jank while typing.
  useEffect(() => {
    if (!scrollRef.current || activeIndex < 0) return;
    const activeEl = navRefs.current.get(activeIndex);
    if (activeEl) {
      activeEl.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [activeIndex]);

  const registerNavRef = useCallback((index: number, el: HTMLElement | null) => {
    if (el) {
      navRefs.current.set(index, el);
    } else {
      navRefs.current.delete(index);
    }
  }, []);

  const persistRecentSearch = useCallback(
    (searchQuery: string) => {
      const cleanQuery = searchQuery.trim();
      if (!cleanQuery) return;
      const newRecent = [
        { query: cleanQuery, timestamp: Date.now() },
        ...recentSearches.filter((s) => s.query !== cleanQuery).slice(0, 4),
      ];
      setRecentSearches(newRecent);
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(newRecent));
        } catch (e) {}
      }
    },
    [recentSearches]
  );

  const navigateToQuery = useCallback(
    (searchQuery: string) => {
      const cleanQuery = searchQuery.trim();
      if (!cleanQuery) return;
      persistRecentSearch(cleanQuery);
      closeSearch();
      const tsPart = timespan !== 'all' ? `&timespan=${timespan}` : '';
      const catApiValue = activeCategory.apiValue;
      const catPart = categoryFilter !== 'all' && catApiValue ? `&category=${encodeURIComponent(catApiValue)}` : '';
      navigate(`${localePathForLang('/', lang)}?q=${encodeURIComponent(cleanQuery)}${tsPart}${catPart}`);
    },
    [activeCategory.apiValue, categoryFilter, closeSearch, lang, persistRecentSearch, timespan]
  );

  const navigateToCluster = useCallback(
    (clusterId: string) => {
      if (!clusterId) return;
      closeSearch();
      navigate(`${localePathForLang(`/cluster/${clusterId}`, lang)}`);
    },
    [closeSearch, lang]
  );

  const filteredActions = useMemo(
    () =>
      SEARCH_ACTIONS.filter(
        (a) =>
          a.label.toLowerCase().includes(query.toLowerCase()) ||
          a.desc.toLowerCase().includes(query.toLowerCase())
      ),
    [SEARCH_ACTIONS, query]
  );

  const onDialogKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const resultCount = suggestions.length + (entityResult ? 1 : 0) + filteredActions.length;
      if (resultCount === 0) return;
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
            if (action) {
              closeSearch();
              navigate(action.href);
            }
          }
        }
      }
    },
    [activeIndex, closeSearch, entityResult, filteredActions, navigateToCluster, navigateToQuery, query, suggestions]
  );

  const previewIndex = useMemo(
    () => (activeIndex === -1 && query.trim().length >= 2 ? 0 : activeIndex),
    [activeIndex, query]
  );

  const selectedItem: SelectedItem | null = useMemo(() => {
    const entityOffset = entityResult ? 1 : 0;
    if (entityResult && previewIndex === 0) {
      return { type: 'ENTITY' as const, data: entityResult };
    }
    if (previewIndex >= entityOffset && previewIndex < entityOffset + suggestions.length) {
      return { type: 'CLUSTER' as const, data: suggestions[previewIndex - entityOffset] };
    }
    if (
      previewIndex >= entityOffset + suggestions.length &&
      previewIndex < entityOffset + suggestions.length + filteredActions.length
    ) {
      return { type: 'ACTION' as const, data: filteredActions[previewIndex - entityOffset - suggestions.length] };
    }
    return null;
  }, [entityResult, previewIndex, suggestions, filteredActions]);

  const handleRemoveRecentSearch = useCallback(
    (searchQuery: string) => {
      const newRecent = recentSearches.filter((item) => item.query !== searchQuery);
      setRecentSearches(newRecent);
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(newRecent));
        } catch (e) {}
      }
    },
    [recentSearches]
  );

  const handleOpenAction = useCallback(
    (href: string) => {
      closeSearch();
      navigate(href);
    },
    [closeSearch]
  );

  const overlayContent = isOpen && (
    <div
      className="fixed inset-0 z-[10000] bg-background/80 backdrop-blur-3xl flex items-center justify-center transition-all animate-in fade-in duration-300 search-overlay-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t('search.dialog_label')}
      onKeyDown={onDialogKeyDown}
      onClick={closeSearch}
    >
      <style
        dangerouslySetInnerHTML={{
          __html: `
            @keyframes searchFadeInUp {
              from {
                opacity: 0;
                transform: translateY(4px);
              }
              to {
                opacity: 1;
                transform: translateY(0);
              }
            }
            .search-animate-item {
              animation: searchFadeInUp 0.18s cubic-bezier(0.16, 1, 0.3, 1) both;
            }
          `,
        }}
      />
      <div
        ref={dialogRef}
        className="search-page-scope w-full max-w-6xl h-[100dvh] sm:h-[92vh] md:h-[80vh] bg-card/85 backdrop-blur-xl border-x border-border/50 sm:border sm:border-border/50 shadow-premium sm:rounded-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 mx-0 sm:mx-4 relative"
        data-page-scope="search"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Flows loading bar at the top */}
        {isLoading && <div className="search-loading-bar" />}
        {/* Command Header */}
        <div className="flex items-center gap-3 px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/10">
          <Search className="hidden sm:block text-muted-foreground" size={24} />
          <SearchInput
            query={query}
            onChange={setQuery}
            inputRef={inputRef}
            isLoading={isLoading}
            placeholder={t('search.input_placeholder')}
          />
          <div className="flex items-center gap-1 sm:gap-[var(--grid-gap)]">
            <button
              onClick={() => setShowFilters(!showFilters)}
              data-testid="search-filter-toggle"
              className={`search-cmd-toolbar-btn p-2 hover:bg-secondary transition-colors ${showFilters ? 'text-muted-foreground' : 'text-muted-foreground'}`}
              title={t('search.filters_title')}
            >
              <SlidersHorizontal size={18} />
            </button>
            <button
              onClick={startVoiceSearch}
              aria-label={isListening ? 'Stop voice search' : 'Start voice search'}
              className={`search-cmd-toolbar-btn p-2 rounded-none hover:bg-secondary transition-colors ${isListening ? 'text-muted-foreground animate-pulse' : 'text-muted-foreground'}`}
            >
              <Mic size={18} />
            </button>
            <button
              onClick={closeSearch}
              className="search-cmd-toolbar-btn p-2 rounded-none hover:bg-secondary text-muted-foreground transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <VoiceSearchOverlay isListening={isListening} onCancel={stopVoiceSearch} t={t} />

        <SearchFilters
          showFilters={showFilters}
          categoryFilter={categoryFilter}
          onCategoryChange={setCategoryFilter}
          timespan={timespan}
          onTimespanChange={setTimespan}
          categories={CATEGORIES}
          timespans={TIMESPANS}
          t={t}
        />

        {/* Main Content Area */}
        <div className="flex-1 overflow-hidden flex">
          <SearchResults
            query={query}
            isLoading={isLoading}
            suggestions={suggestions}
            entityResult={entityResult}
            filteredActions={filteredActions}
            searchActions={SEARCH_ACTIONS}
            recentSearches={recentSearches}
            trendingItems={trendingItems}
            activeIndex={activeIndex}
            registerNavRef={registerNavRef}
            onSearchAll={() => navigateToQuery(query)}
            onNavigateToCluster={navigateToCluster}
            onNavigateToQuery={navigateToQuery}
            onSetQuery={setQuery}
            onRemoveRecentSearch={handleRemoveRecentSearch}
            onClearRecentSearches={handleClearRecentSearches}
            searchTime={searchTime}
            closeSearch={closeSearch}
            t={t}
            scrollRef={scrollRef}
          />

          <SearchPreview
            item={selectedItem}
            t={t}
            lang={lang}
            onOpenCluster={navigateToCluster}
            onOpenEntity={navigateToQuery}
            onOpenAction={handleOpenAction}
          />
        </div>

        <SearchFooter t={t} />
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
            <span className="search-trigger-hint">{t('search.hint_topics')}</span>
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
