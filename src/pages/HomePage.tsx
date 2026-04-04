import React, { useState, useEffect, useCallback, useRef } from 'react';
import { SlidersHorizontal, RefreshCw, X } from 'lucide-react';
import { apiClient } from '../api/client';
import { ClusterCard } from '../components/ClusterCard';
import { TrendingSidebar } from '../components/TrendingSidebar';
import { Header } from '../components/Header';
import { useNewsStore, useUIStore } from '../store/useNewsStore';
import { useSSE } from '../hooks/useSSE';

const TOPICS = ['Политика', 'Економија', 'Технологија', 'Спорт', 'Забава', 'Здравје'];

export const HomePage: React.FC = () => {
  const {
    clusters, isLoading, error, page, pageSize, hasMore,
    setClusters, addClusters, setLoading, setError,
    setPage, setHasMore, setTotalClusters, reset,
  } = useNewsStore();

  const { selectedCategory, selectedTopic, searchQuery, setSearchQuery } = useUIStore();
  const [sortBy, setSortBy] = useState<'recent' | 'popular'>('recent');
  const [showTopicBar, setShowTopicBar] = useState(false);
  const [newArticlesBanner, setNewArticlesBanner] = useState(0);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const hydrated = useRef(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchNews = useCallback(async (pg = 0, append = false) => {
    // ... rest of fetchNews (unchanged)

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    try {
      const response = await apiClient.getNews({
        country: selectedCategory,
        topic: selectedTopic || undefined,
        q: searchQuery || undefined,
        sort: sortBy,
        page: pg,
        page_size: pageSize,
      }, { signal: controller.signal });

      if (append) addClusters(response.clusters);
      else setClusters(response.clusters);
      
      setPage(pg);
      setHasMore(response.has_more);
      setTotalClusters(response.total_clusters);
      setError(null);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Грешка при вчитување');
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [selectedCategory, selectedTopic, searchQuery, sortBy]);

  useEffect(() => {
    if (!hydrated.current && window.__INITIAL_DATA__ && window.__INITIAL_DATA__.clusters?.length > 0) {
      // Use SSR data
      if (!selectedTopic && !searchQuery && page === 0 && selectedCategory === 'Македонија') {
        setClusters(window.__INITIAL_DATA__.clusters);
        hydrated.current = true;
        return;
      }
    }

    reset();
    fetchNews(0, false);
    hydrated.current = true;
  }, [selectedCategory, selectedTopic, searchQuery, sortBy]);

  const loadMore = useCallback(() => {
    if (!isLoading && hasMore) fetchNews(page + 1, true);
  }, [isLoading, hasMore, fetchNews, page]);

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: '200px' }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  // SSE live updates
  const handleSSEUpdate = useCallback((data: { cluster_id: string; new_articles: number }) => {
    setNewArticlesBanner((prev) => prev + (data.new_articles || 1));
  }, []);
  useSSE('/api/live', handleSSEUpdate);

  const isSearching = !!searchQuery;
  const heroCluster = clusters[0];
  const featuredClusters = clusters.slice(1, 7);
  const listClusters = clusters.slice(7);

  return (
    <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
      <Header />

      <main className="page-container py-6">
        {/* Live update banner */}
        {newArticlesBanner > 0 && (
          <div
            onClick={() => { setNewArticlesBanner(0); fetchNews(0, false); }}
            className="mb-4 cursor-pointer rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold px-4 py-2.5 flex items-center justify-between transition-colors"
          >
            <span>⚡ {newArticlesBanner} нови вести — Притиснете за освежување</span>
            <X size={16} />
          </div>
        )}

        {/* Search result header */}
        {isSearching && (
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-ink-muted dark:text-slate-400">
                Резултати за:{' '}
                <span className="font-bold text-ink dark:text-slate-100">&ldquo;{searchQuery}&rdquo;</span>
                {' '}— {clusters.length} кластери
              </p>
            </div>
            <button
              onClick={() => { setSearchQuery(''); reset(); }}
              className="btn-outline text-xs"
            >
              Исчисти
            </button>
          </div>
        )}

        {/* Toolbar row */}
        <div className="flex items-center justify-between gap-3 mb-5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTopicBar(!showTopicBar)}
              className={`btn text-sm gap-1.5 ${showTopicBar ? 'btn-primary' : 'btn-outline'}`}
            >
              <SlidersHorizontal size={14} />
              Теми
            </button>
            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'recent' | 'popular')}
              className="input w-auto text-sm py-1.5"
            >
              <option value="recent">Најнови</option>
              <option value="popular">Популарни</option>
            </select>
          </div>

          <button
            onClick={() => fetchNews(0, false)}
            disabled={isLoading}
            className="btn-ghost text-sm"
            title="Освежи"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Topic filter bar */}
        {showTopicBar && (
          <div className="flex flex-wrap gap-2 mb-5 animate-fade-in">
            <button
              onClick={() => useUIStore.setState({ selectedTopic: '' })}
              className={!selectedTopic ? 'pill-active' : 'pill-inactive'}
            >
              Сите
            </button>
            {TOPICS.map((t) => (
              <button
                key={t}
                onClick={() => useUIStore.setState({ selectedTopic: t })}
                className={selectedTopic === t ? 'pill-active' : 'pill-inactive'}
              >
                {t}
              </button>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-5 rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800 p-4 text-sm text-brand-700 dark:text-brand-300">
            {error}
          </div>
        )}

        {/* Main layout */}
        {isLoading && clusters.length === 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2 space-y-5">
              <div className="skeleton rounded-2xl" style={{ height: 480 }} />
              <div className="grid grid-cols-2 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="skeleton rounded-xl" style={{ height: 280 }} />
                ))}
              </div>
            </div>
            <div className="space-y-4">
              <div className="skeleton rounded-xl" style={{ height: 300 }} />
              <div className="skeleton rounded-xl" style={{ height: 140 }} />
            </div>
          </div>
        ) : clusters.length === 0 ? (
          <div className="card p-12 text-center">
            <p className="text-2xl mb-2">📭</p>
            <p className="font-semibold text-ink dark:text-slate-200 mb-1">Нема вести</p>
            <p className="text-sm text-ink-muted dark:text-slate-500">Нема резултати за оваа комбинација</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Left: main feed */}
            <div className="lg:col-span-2 space-y-5">
              {/* Hero */}
              {heroCluster && (
                <ClusterCard cluster={heroCluster} variant="hero" />
              )}

              {/* Featured 2-col grid */}
              {featuredClusters.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {featuredClusters.map((c) => (
                    <ClusterCard key={c.cluster_id} cluster={c} variant="featured" />
                  ))}
                </div>
              )}

              {/* Compact list for remaining */}
              {listClusters.length > 0 && (
                <div className="card divide-y divide-surface-3 dark:divide-dark-3">
                  <div className="px-4 py-3">
                    <p className="section-heading">Повеќе вести</p>
                  </div>
                  {listClusters.map((c) => (
                    <div key={c.cluster_id} className="px-2 py-1">
                      <ClusterCard cluster={c} variant="compact" />
                    </div>
                  ))}
                </div>
              )}

              {/* Infinite scroll sentinel */}
              <div ref={sentinelRef} className="h-8 w-full" />
              {isLoading && clusters.length > 0 && (
                <div className="text-center py-4 text-sm text-ink-muted dark:text-slate-500 flex items-center justify-center gap-2">
                  <RefreshCw size={14} className="animate-spin" />
                  Вчитување...
                </div>
              )}
            </div>

            {/* Right: sidebar */}
            <div className="lg:col-span-1">
              <div className="lg:sticky lg:top-20">
                <TrendingSidebar />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
