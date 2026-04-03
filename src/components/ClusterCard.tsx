import React from 'react';
import { NewsCluster } from '../types';
import { ArticleCard } from './ArticleCard';
import { apiClient } from '../api/client';

interface ClusterCardProps {
  cluster: NewsCluster;
  onArticleClick: (link: string) => void;
  onDetailClick: (clusterId: string) => void;
}

export const ClusterCard: React.FC<ClusterCardProps> = ({
  cluster,
  onArticleClick,
  onDetailClick,
}) => {
  const imageUrl = apiClient.getImageUrl(cluster.representative_image, 600);
  const breakingStyle = cluster.is_breaking
    ? 'border-l-4 border-red-600 bg-red-50'
    : 'border-l-4 border-gray-300';

  return (
    <div className={`bg-white rounded-lg shadow-md overflow-hidden ${breakingStyle} mb-4`}>
      {/* Header with image */}
      {imageUrl && (
        <div className="relative w-full h-80 bg-gray-300 overflow-hidden">
          <img
            src={imageUrl}
            alt="Cluster"
            className="w-full h-full object-cover"
          />
          {cluster.is_breaking && (
            <div className="absolute top-4 left-4 bg-red-600 text-white font-bold px-4 py-2 rounded-full text-sm">
              🔥 BREAKING
            </div>
          )}
        </div>
      )}

      <div className="p-6">
        {/* Cluster info */}
        <div className="flex justify-between items-start mb-3">
          <div>
            <p className="text-xs text-gray-500 mb-1">
              {cluster.articles.length} статии · Скор: {cluster.score.toFixed(2)}
            </p>
            <h2 className="text-2xl font-bold mb-2">{cluster.articles[0]?.title || 'Вести'}</h2>
          </div>
          {cluster.has_synthesis && (
            <div className="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full text-xs font-semibold">
              ✨ Синтеза
            </div>
          )}
        </div>

        {/* Description */}
        {cluster.articles[0]?.description && (
          <p className="text-gray-700 mb-4 line-clamp-3">{cluster.articles[0].description}</p>
        )}

        {/* Article list */}
        <div className="mb-4 border-t pt-4">
          <p className="text-sm font-semibold text-gray-600 mb-3">Поврзани статии:</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {cluster.articles.slice(0, 4).map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                onClick={() => onArticleClick(article.link)}
              />
            ))}
          </div>
          {cluster.articles.length > 4 && (
            <p className="text-xs text-gray-500 mt-3">
              +{cluster.articles.length - 4} повеќе статии...
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-4 border-t">
          <button
            onClick={() => onDetailClick(cluster.cluster_id)}
            className="flex-1 bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition font-semibold"
          >
            Детали & Синтеза →
          </button>
          <button
            onClick={() => onArticleClick(cluster.articles[0]?.link || '#')}
            className="flex-1 bg-gray-200 text-gray-800 py-2 px-4 rounded-lg hover:bg-gray-300 transition"
          >
            Прочитај прва статија
          </button>
        </div>
      </div>
    </div>
  );
};
