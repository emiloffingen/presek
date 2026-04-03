import React from 'react';
import { NewsCluster } from '../types';
import { ArticleCard } from './ArticleCard';
import { apiClient } from '../api/client';
import { Flame, Sparkles, ArrowRight, FileText } from 'lucide-react';

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
    ? 'border-l-4 border-red-600 bg-red-50 dark:bg-red-950'
    : 'border-l-4 border-gray-300 dark:border-gray-600';

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden ${breakingStyle} mb-4`}>
      {/* Header with image */}
      {imageUrl && (
        <div className="relative w-full h-80 bg-gray-300 dark:bg-gray-700 overflow-hidden">
          <img
            src={imageUrl}
            alt="Cluster"
            className="w-full h-full object-cover"
          />
          {cluster.is_breaking && (
            <div className="absolute top-4 left-4 bg-red-600 text-white font-bold px-4 py-2 rounded-full text-sm flex items-center gap-2">
              <Flame size={18} />
              BREAKING
            </div>
          )}
        </div>
      )}

      <div className="p-6">
        {/* Cluster info */}
        <div className="flex justify-between items-start mb-3">
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
              <FileText className="inline mr-1" size={14} />
              {cluster.articles.length} статии · Скор: {cluster.score.toFixed(2)}
            </p>
            <h2 className="text-2xl font-bold mb-2 text-gray-900 dark:text-white">{cluster.articles[0]?.title || 'Вести'}</h2>
          </div>
          {cluster.has_synthesis && (
            <div className="bg-accent-100 dark:bg-accent-900 text-accent-800 dark:text-accent-200 px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1">
              <Sparkles size={14} />
              Синтеза
            </div>
          )}
        </div>

        {/* Description */}
        {cluster.articles[0]?.description && (
          <p className="text-gray-700 dark:text-gray-300 mb-4 line-clamp-3">{cluster.articles[0].description}</p>
        )}

        {/* Article list */}
        <div className="mb-4 border-t dark:border-gray-700 pt-4">
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-3">Поврзани статии:</p>
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
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
              +{cluster.articles.length - 4} повеќе статии...
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-4 border-t dark:border-gray-700">
          <button
            onClick={() => onDetailClick(cluster.cluster_id)}
            className="flex-1 bg-primary-600 hover:bg-primary-700 dark:bg-primary-700 dark:hover:bg-primary-600 text-white py-2 px-4 rounded-lg transition font-semibold flex items-center justify-center gap-2"
          >
            Детали & Синтеза
            <ArrowRight size={18} />
          </button>
          <button
            onClick={() => onArticleClick(cluster.articles[0]?.link || '#')}
            className="flex-1 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 py-2 px-4 rounded-lg transition"
          >
            Прочитај прва статија
          </button>
        </div>
      </div>
    </div>
  );
};
