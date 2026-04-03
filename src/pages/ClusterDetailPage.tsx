import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 text-lg mb-4">⏳ Вчитување...</p>
          <div className="w-12 h-12 border-4 border-blue-300 border-t-blue-600 rounded-full animate-spin mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !cluster) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 text-lg mb-4">❌ {error || 'Кластерот не е пронајден'}</p>
          <button
            onClick={() => navigate('/')}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            ← Назад на почеток
          </button>
        </div>
      </div>
    );
  }

  const imageUrl = apiClient.getImageUrl(cluster.representative_image, 800);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-md sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <button
            onClick={() => navigate(-1)}
            className="text-blue-600 hover:text-blue-800 font-semibold mb-2"
          >
            ← Назад
          </button>
          <h1 className="text-2xl font-bold">{cluster.articles[0]?.title || 'Детал'}</h1>
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
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <div className="flex gap-2 mb-2">
                {cluster.is_breaking && (
                  <span className="bg-red-600 text-white px-3 py-1 rounded-full text-sm font-bold">
                    🔥 BREAKING
                  </span>
                )}
                {cluster.has_synthesis && (
                  <span className="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full text-sm font-semibold">
                    ✨ Има синтеза
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600">
                Скор: <span className="font-bold">{cluster.score.toFixed(2)}</span> · Статии:{' '}
                <span className="font-bold">{cluster.articles.length}</span> · Време за читање:{' '}
                <span className="font-bold">{cluster.total_reading_time} мин</span>
              </p>
            </div>
          </div>

          {/* Tags */}
          {cluster.tags.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-semibold text-gray-600 mb-2">Етикети:</p>
              <div className="flex gap-2 flex-wrap">
                {cluster.tags.map((tag, idx) => (
                  <span
                    key={idx}
                    className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-xs"
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
          <div className="bg-yellow-50 border-2 border-yellow-200 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-bold mb-4">✨ АИ Синтеза</h2>
            <p className="text-gray-700 mb-4 leading-relaxed">{cluster.synthesis}</p>

            {/* Perspectives */}
            {cluster.perspectives.length > 0 && (
              <div className="mt-4">
                <h3 className="font-semibold text-gray-800 mb-3">Различни пикови:</h3>
                <div className="space-y-3">
                  {cluster.perspectives.map((perspective, idx) => (
                    <div
                      key={idx}
                      className="bg-white border-l-4 border-yellow-500 p-4 rounded"
                    >
                      <p className="font-semibold text-gray-800">{perspective.angle}</p>
                      <p className="text-gray-600 text-sm mt-2">{perspective.content}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Chat section */}
        <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-bold mb-4">🤖 Прашај ЈИ за овој кластер</h2>
          <form onSubmit={handleChat} className="flex gap-2 mb-4">
            <input
              type="text"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              placeholder="Прашај нешто за овие вести..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={chatLoading}
            />
            <button
              type="submit"
              disabled={chatLoading || !chatQuery.trim()}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition disabled:bg-gray-400"
            >
              {chatLoading ? '⏳' : 'Прашај'}
            </button>
          </form>
          {chatResponse && (
            <div className="bg-white border-l-4 border-blue-500 p-4 rounded">
              <p className="text-gray-700">{chatResponse}</p>
            </div>
          )}
        </div>

        {/* Articles */}
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-4">📰 Сите статии в кластерот</h2>
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
            <h2 className="text-xl font-bold mb-4">🔗 Поврзани кластери</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cluster.related.map((related) => (
                <div
                  key={related.cluster_id}
                  onClick={() => navigate(`/cluster/${related.cluster_id}`)}
                  className="bg-white rounded-lg shadow-md p-4 cursor-pointer hover:shadow-lg transition"
                >
                  {related.image_url && (
                    <img
                      src={apiClient.getImageUrl(related.image_url, 400)}
                      alt={related.title}
                      className="w-full h-32 object-cover rounded mb-2"
                    />
                  )}
                  <p className="font-semibold">{related.title}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
