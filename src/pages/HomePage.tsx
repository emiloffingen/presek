import React, { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Sparkles, Zap } from 'lucide-react';
import { apiClient } from '../api/client';
import { ClusterCard } from '../components/ClusterCard';
import { TrendingSidebar } from '../components/TrendingSidebar';
import { Header } from '../components/Header';
import { useNewsStore, useUIStore } from '../store/useNewsStore';
import { useSSE } from '../hooks/useSSE';

const CATEGORIES = [
  'Македонија', 'Балкан', 'Европа', 'Свет', 'Економија', 'Спорт', 'Технологија'
];

export const HomePage: React.FC = () => {
  // Granular selectors — re-render only when these specific slices change.
  const clusters = useNewsStore(s => s.clusters);
  const isLoading = useNewsStore(s => s.isLoading);
  const error = useNewsStore(s => s.error);
  const page = useNewsStore(s => s.page);
  const hasMore = useNewsStore(s => s.hasMore);
  const setClusters = useNewsStore(s => s.setClusters);
  const addClusters = useNewsStore(s => s.addClusters);
  const setLoading = useNewsStore(s => s.setLoading);
  const setError = useNewsStore(s => s.setError);
  const setHasMore = useNewsStore(s => s.setHasMore);
  const setPage = useNewsStore(s => s.setPage);
  const reset = useNewsStore(s => s.reset);

  const selectedCategory = useUIStore(s => s.selectedCategory);
  const selectedTopic = useUIStore(s => s.selectedTopic);
  const searchQuery = useUIStore(s => s.searchQuery);
  const trackInterest = useUIStore(s => s.trackInterest);
  const getTopInterests = useUIStore(s => s.getTopInterests);

  const [sortBy, setSortBy] = useState<'recent' | 'popular'>('recent');
  const [newArticlesCount, setNewArticlesCount] = useState(0);
  const [forYouClusters, setForYouClusters] = useState<any[]>([]);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const hydrated = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sectionTitle = searchQuery
    ? `РЕЗУЛТАТИ ЗА: ${searchQuery}`
    : selectedTopic
      ? selectedTopic
      : !selectedCategory || selectedCategory === 'Македонија' || selectedCategory === 'Сите'
        ? 'ГЛАВНИ ВЕСТИ'
        : selectedCategory;

  // SSE for live updates
  useSSE('/api/live', (data: any) => {
    if (data.type === 'new_articles') {
      setNewArticlesCount(prev => prev + data.count);
    }
  });

  const fetchNews = useCallback(async (pg = 0, append = false) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    try {
      const res = await apiClient.getNews({
        page: pg,
        page_size: 24,
        category: selectedCategory === 'Сите' ? '' : selectedCategory,
        topic: selectedTopic,
        q: searchQuery,
        sort: sortBy
      }, { signal: controller.signal });

      if (append) {
        addClusters(res.clusters);
      } else {
        setClusters(res.clusters);
      }
      setHasMore(res.clusters.length === 24);
      setPage(pg);
      setError(null);
    } catch (err: any) {
      if (err.name !== 'CanceledError') {
        setError(err.message || 'Грешка при вчитување');
      }
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, selectedTopic, searchQuery, sortBy, addClusters, setClusters, setHasMore, setPage, setError, setLoading]);

  // Personalized "For You" fetch
  useEffect(() => {
    const interests = getTopInterests();
    const { recentlyRead } = useUIStore.getState();
    
    if ((interests.length > 0 || recentlyRead.length > 0) && selectedCategory === 'Македонија' && !searchQuery && !selectedTopic) {
      apiClient.getRecommendations({
        recentlyRead,
        followedTopics: interests,
        limit: 6
      }).then(res => setForYouClusters(res.clusters)).catch(() => {});
    } else {
      setForYouClusters([]);
    }
  }, [selectedCategory, searchQuery, selectedTopic, getTopInterests]);

  // Track category interest
  useEffect(() => {
    if (selectedCategory && selectedCategory !== 'Македонија') {
      trackInterest(selectedCategory);
    }
    if (selectedTopic) {
      trackInterest(selectedTopic);
    }
  }, [selectedCategory, selectedTopic, trackInterest]);

  useEffect(() => {
    if (!hydrated.current && window.__INITIAL_DATA__ && window.__INITIAL_DATA__.clusters?.length > 0) {
      if (!selectedTopic && !searchQuery && page === 0 && selectedCategory === 'Македонија') {
        setClusters(window.__INITIAL_DATA__.clusters);
        hydrated.current = true;
        return;
      }
    }

    reset();
    fetchNews(0, false);
    hydrated.current = true;
  }, [selectedCategory, selectedTopic, searchQuery, sortBy, reset, fetchNews]);

  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !isLoading && hasMore) {
        fetchNews(page + 1, true);
      }
    }, { threshold: 0.1 });

    if (sentinelRef.current) {
      observer.observe(sentinelRef.current);
    }
    return () => observer.disconnect();
  }, [isLoading, hasMore, page, fetchNews]);

  return (
    <div className="min-h-screen bg-primary">
      <Header />
      
      <main className="site-layout py-4">
        {/* SSE Toast */}
        {newArticlesCount > 0 && (
          <button 
            onClick={() => { setNewArticlesCount(0); reset(); fetchNews(0, false); window.scrollTo({top:0, behavior:'smooth'}); }}
            className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 bg-accent text-white px-6 py-3 rounded-full shadow-2xl flex items-center gap-3 animate-bounce font-bold uppercase text-xs tracking-widest"
          >
            <Zap size={16} fill="white" />
            {newArticlesCount} нови вести
          </button>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-9">
            
            {/* Personalization Section */}
            {forYouClusters.length > 0 && (
              <section className="mb-8 bg-secondary/30 p-4 lg:p-5 border-y-2 border-primary">
                <div className="flex items-center gap-2 mb-4">
                  <Sparkles className="text-accent" size={18} />
                  <h2 className="rail-label m-0">ПРЕПОРАЧАНО ЗА ВАС</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {forYouClusters.map(cluster => (
                    <ClusterCard 
                      key={cluster.cluster_id} 
                      cluster={cluster} 
                      compact 
                      reason={cluster.reason}
                    />
                  ))}
                </div>
              </section>
            )}

            <div className="flex justify-between items-center mb-5 border-b border-color pb-3">
              <h1 className="rail-label m-0">
                {sectionTitle}
              </h1>
              
              <div className="flex items-center gap-4">
                <select 
                  value={sortBy} 
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="bg-transparent border-none text-[10px] font-black uppercase tracking-widest text-primary focus:outline-none cursor-pointer"
                >
                  <option value="recent">Најнови</option>
                  <option value="popular">Популарни</option>
                </select>
              </div>
            </div>

            {error && (
              <div className="bg-secondary p-10 text-center border-t-2 border-accent mb-8">
                <p className="text-accent font-bold uppercase tracking-widest">{error}</p>
                <button onClick={() => fetchNews(0)} className="mt-4 flex items-center gap-2 mx-auto text-[10px] font-black uppercase text-primary hover:underline">
                  <RefreshCw size={12} /> Обиди се повторно
                </button>
              </div>
            )}

            <div className="news-feed-grid">
              {clusters.map((cluster, idx) => (
                <ClusterCard 
                  key={cluster.cluster_id} 
                  cluster={cluster} 
                  isLead={idx === 0 && !searchQuery && !selectedTopic}
                />
              ))}
            </div>

            {isLoading && (
              <div className="news-feed-grid mt-8">
                {[1, 2, 3].map(i => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-video bg-secondary mb-4 rounded-sm" />
                    <div className="h-4 bg-secondary w-3/4 mb-2" />
                    <div className="h-4 bg-secondary w-1/2" />
                  </div>
                ))}
              </div>
            )}

            <div ref={sentinelRef} className="h-20" />
          </div>

          <aside className="lg:col-span-3">
            <TrendingSidebar />
          </aside>
        </div>
      </main>
    </div>
  );
};
