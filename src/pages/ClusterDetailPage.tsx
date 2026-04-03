import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Flame, Sparkles, Newspaper, Link2, MessageCircle, Loader2 } from 'lucide-react';
import { apiClient } from '../api/client';
import { ClusterDetail, ChatResponse } from '../types';
import { ArticleCard } from '../components/ArticleCard';

export const ClusterDetailPage: React.FC = () => {
  const { clusterId } = useParams<{ clusterId: string }>();
  const navigate = useNavigate();
  const [cluster, setCluster] = useState<ClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatQuery, setChatQuery] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResponse, setChatResponse] = useState<string | null>(null);

  useEffect(() => {
    const fetchCluster = async () => {
      if (!clusterId) return;
      try {
        setLoading(true);
        const response = await apiClient.getClusterDetail(clusterId);
        setCluster(response.data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load cluster');
      } finally {
        setLoading(false);
      }
    };

    fetchCluster();
  }, [clusterId]);

  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatQuery.trim() || !clusterId) return;

    try {
      setChatLoading(true);
      const response = await apiClient.chatCluster(clusterId, chatQuery);
      setChatResponse(response.response);
    } catch (err) {
      setChatResponse('Грешка при обработката на прашањето. Попробајте повторно.');
    } finally {
      setChatLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">Вчитување...</p>
          <Loader2 className="w-12 h-12 animate-spin mx-auto text-primary-600 dark:text-primary-400" />
        </div>
      </div>
    );
  }

  if (error || !cluster) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 text-lg mb-4">{error || 'Кластерот не е пронајден'}</p>
          <button
            onClick={() => navigate('/')}
            className="bg-primary-600 dark:bg-primary-700 text-white px-6 py-2 rounded-lg hover:bg-primary-700 dark:hover:bg-primary-600 transition inline-flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Назад на почеток
          </button>
        </div>
      </div>
    );
  }

  const imageUrl = apiClient.getImageUrl(cluster.representative_image, 800);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-md sticky top-0 z-40 border-b dark:border-gray-700">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <button
            onClick={() => navigate(-1)}
            className="text-primary-600 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-300 font-semibold mb-2 inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" />
            Назад
          </button>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{cluster.articles[0]?.title || 'Детал'}</h1>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Main image */}
        {imageUrl && (
          <div className="mb-6 rounded-lg overflow-hidden shadow-lg">
            <img src={imageUrl} alt="Cluster" className="w-full h-96 object-cover" />
          </div>
        )}

        {/* Cluster info */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6 border dark:border-gray-700">
          <div className="flex justify-between items-start mb-4">
            <div>
              <div className="flex gap-2 mb-2">
                {cluster.is_breaking && (
                  <span className="bg-red-600 dark:bg-red-700 text-white px-3 py-1 rounded-full text-sm font-bold inline-flex items-center gap-1">
                    <Flame className="w-4 h-4" />
                    BREAKING
                  </span>
                )}
                {cluster.has_synthesis && (
                  <span className="bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 px-3 py-1 rounded-full text-sm font-semibold inline-flex items-center gap-1">
                    <Sparkles className="w-4 h-4" />
                    Има синтеза
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Скор: <span className="font-bold">{cluster.score.toFixed(2)}</span> · Статии:{' '}
                <span className="font-bold">{cluster.articles.length}</span> · Време за читање:{' '}
                <span className="font-bold">{cluster.total_reading_time} мин</span>
              </p>
            </div>
          </div>

          {/* Tags */}
          {cluster.tags.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Етикети:</p>
              <div className="flex gap-2 flex-wrap">
                {cluster.tags.map((tag, idx) => (
                  <span
                    key={idx}
                    className="bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-200 px-3 py-1 rounded-full text-xs"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Synthesis */}
        {cluster.has_synthesis && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border-2 border-yellow-200 dark:border-yellow-700 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white inline-flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              АИ Синтеза
            </h2>
            <p className="text-gray-700 dark:text-gray-300 mb-4 leading-relaxed">{cluster.synthesis}</p>

            {/* Perspectives */}
            {cluster.perspectives.length > 0 && (
              <div className="mt-4">
                <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-3">Различни пикови:</h3>
                <div className="space-y-3">
                  {cluster.perspectives.map((perspective, idx) => (
                    <div
                      key={idx}
                      className="bg-white dark:bg-gray-800 border-l-4 border-yellow-500 dark:border-yellow-600 p-4 rounded"
                    >
                      <p className="font-semibold text-gray-800 dark:text-gray-100">{perspective.angle}</p>
                      <p className="text-gray-600 dark:text-gray-400 text-sm mt-2">{perspective.content}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Chat section */}
        <div className="bg-primary-50 dark:bg-primary-900/20 border-2 border-primary-200 dark:border-primary-700 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white inline-flex items-center gap-2">
            <MessageCircle className="w-5 h-5" />
            Прашај ЈИ за овој кластер
          </h2>
          <form onSubmit={handleChat} className="flex gap-2 mb-4">
            <input
              type="text"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              placeholder="Прашај нешто за овие вести..."
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
              disabled={chatLoading}
            />
            <button
              type="submit"
              disabled={chatLoading || !chatQuery.trim()}
              className="bg-primary-600 dark:bg-primary-700 text-white px-6 py-2 rounded-lg hover:bg-primary-700 dark:hover:bg-primary-600 transition disabled:bg-gray-400 dark:disabled:bg-gray-600 inline-flex items-center gap-2"
            >
              {chatLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Прашај
            </button>
          </form>
          {chatResponse && (
            <div className="bg-white dark:bg-gray-800 border-l-4 border-primary-500 dark:border-primary-600 p-4 rounded">
              <p className="text-gray-700 dark:text-gray-300">{chatResponse}</p>
            </div>
          )}
        </div>

        {/* Articles */}
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white inline-flex items-center gap-2">
            <Newspaper className="w-5 h-5" />
            Сите статии в кластерот
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cluster.articles.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                onClick={() => window.open(article.link, '_blank')}
              />
            ))}
          </div>
        </div>

        {/* Related clusters */}
        {cluster.related.length > 0 && (
          <div className="mb-6">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white inline-flex items-center gap-2">
              <Link2 className="w-5 h-5" />
              Поврзани кластери
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cluster.related.map((related) => (
                <div
                  key={related.cluster_id}
                  onClick={() => navigate(`/cluster/${related.cluster_id}`)}
                  className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 cursor-pointer hover:shadow-lg transition border dark:border-gray-700"
                >
                  {related.image_url && (
                    <img
                      src={apiClient.getImageUrl(related.image_url, 400)}
                      alt={related.title}
                      className="w-full h-32 object-cover rounded mb-2"
                    />
                  )}
                  <p className="font-semibold text-gray-900 dark:text-white">{related.title}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
