import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { ClusterCard } from '../components/ClusterCard';
import { TrendingSidebar } from '../components/TrendingSidebar';
import { useNewsStore, useUIStore } from '../store/useNewsStore';

const CATEGORIES = ['Македонија', 'Балкан', 'Европа', 'Германија', 'Америка', 'Свет'];
const TOPICS = ['Политика', 'Економија', 'Технологија', 'Спорт', 'Забава', 'Здравје'];

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const {
    clusters,
    isLoading,
    error,
    page,
    pageSize,
    hasMore,
    setClusters,
    addClusters,
    setLoading,
    setError,
    setPage,
    setHasMore,
    setTotalClusters,
    reset,
  } = useNewsStore();

  const { selectedCategory, selectedTopic, searchQuery, setSelectedCategory, setSearchQuery } =
    useUIStore();
  const [sortBy, setSortBy] = useState<'recent' | 'popular'>('recent');

  // Fetch news on category/topic/search change
  useEffect(() => {
    const fetchNews = async () => {
      try {
        setLoading(true);
        const response = await apiClient.getNews({
          country: selectedCategory === 'Свет' ? undefined : selectedCategory,
          category: selectedCategory,
          topic: selectedTopic || undefined,
          q: searchQuery || undefined,
          sort: sortBy,
          page: 0,
          page_size: pageSize,
        });

        setClusters(response.clusters);
        setPage(0);
        setHasMore(response.has_more);
        setTotalClusters(response.total_clusters);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch news');
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [selectedCategory, selectedTopic, searchQuery, sortBy]);

  const loadMore = async () => {
    if (isLoading || !hasMore) return;

    try {
      setLoading(true);
      const nextPage = page + 1;
      const response = await apiClient.getNews({
        country: selectedCategory === 'Свет' ? undefined : selectedCategory,
        category: selectedCategory,
        topic: selectedTopic || undefined,
        q: searchQuery || undefined,
        sort: sortBy,
        page: nextPage,
        page_size: pageSize,
      });

      addClusters(response.clusters);
      setPage(nextPage);
      setHasMore(response.has_more);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more');
    } finally {
      setLoading(false);
    }
  };

  const handleArticleClick = (link: string) => {
    window.open(link, '_blank');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h1 className="text-3xl font-bold text-blue-600 mb-4">📰 Presek</h1>

          {/* Search bar */}
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder="Пребарај вести..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
              🔍 Барај
            </button>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCategory(cat);
                  reset();
                }}
                className={`px-4 py-2 rounded-full whitespace-nowrap transition font-semibold ${
                  selectedCategory === cat
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main content */}
          <div className="lg:col-span-2">
            {/* Topic filters */}
            {selectedCategory !== 'Свет' && (
              <div className="mb-4 bg-white p-4 rounded-lg shadow-md">
                <p className="text-sm font-semibold text-gray-600 mb-2">Филтрирај по тема:</p>
                <div className="flex gap-2 overflow-x-auto">
                  <button
                    onClick={() => useUIStore.setState({ selectedTopic: '' })}
                    className={`px-3 py-1 rounded-full text-sm whitespace-nowrap transition ${
                      !selectedTopic
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                    }`}
                  >
                    Сите
                  </button>
                  {TOPICS.map((topic) => (
                    <button
                      key={topic}
                      onClick={() => useUIStore.setState({ selectedTopic: topic })}
                      className={`px-3 py-1 rounded-full text-sm whitespace-nowrap transition ${
                        selectedTopic === topic
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                      }`}
                    >
                      {topic}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Sort options */}
            <div className="mb-4 flex justify-between items-center">
              <p className="text-sm text-gray-600">
                Вкупно: <span className="font-bold">{clusters.length}</span> кластери
              </p>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'recent' | 'popular')}
                className="px-3 py-1 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="recent">🕐 Најскорешни</option>
                <option value="popular">👍 Популарни</option>
              </select>
            </div>

            {/* Error message */}
            {error && (
              <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg mb-4">
                ⚠️ {error}
              </div>
            )}

            {/* News clusters */}
            {isLoading && clusters.length === 0 ? (
              <div className="space-y-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-96 bg-gray-200 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : clusters.length === 0 ? (
              <div className="bg-white rounded-lg shadow-md p-8 text-center">
                <p className="text-gray-500 text-lg">Нема вести за оваа категорија</p>
              </div>
            ) : (
              <>
                {clusters.map((cluster) => (
                  <ClusterCard
                    key={cluster.cluster_id}
                    cluster={cluster}
                    onArticleClick={handleArticleClick}
                    onDetailClick={(clusterId) => navigate(`/cluster/${clusterId}`)}
                  />
                ))}

                {/* Load more button */}
                {hasMore && (
                  <div className="text-center mt-6">
                    <button
                      onClick={loadMore}
                      disabled={isLoading}
                      className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition disabled:bg-gray-400 font-semibold"
                    >
                      {isLoading ? '⏳ Вчитување...' : '📥 Вчитај повеќе'}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <TrendingSidebar />

            {/* Quick links */}
            <div className="mt-6 bg-white rounded-lg shadow-md p-4 sticky top-24">
              <h3 className="font-bold text-lg mb-3">⚡ Брзи врски</h3>
              <div className="space-y-2">
                <button
                  onClick={() => navigate('/stats')}
                  className="w-full text-left px-4 py-2 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition"
                >
                  📊 Статистика
                </button>
                <button
                  onClick={() => navigate('/briefing')}
                  className="w-full text-left px-4 py-2 bg-green-50 text-green-600 rounded hover:bg-green-100 transition"
                >
                  📋 Дневен преглед
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
