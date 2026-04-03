import React from 'react';
import { Article } from '../types';
import { apiClient } from '../api/client';

interface ArticleCardProps {
  article: Article;
  onClick?: () => void;
}

export const ArticleCard: React.FC<ArticleCardProps> = ({ article, onClick }) => {
  const imageUrl = apiClient.getImageUrl(article.image_url, 400);

  return (
    <article
      className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
      onClick={onClick}
    >
      {imageUrl && (
        <div className="relative w-full h-48 bg-gray-200 overflow-hidden">
          <img
            src={imageUrl}
            alt={article.title}
            className="w-full h-full object-cover hover:scale-105 transition-transform"
          />
          <div className="absolute top-2 right-2 bg-black bg-opacity-60 text-white text-xs px-2 py-1 rounded">
            {article.reading_time} мин
          </div>
        </div>
      )}
      <div className="p-4">
        <div className="flex gap-2 mb-2">
          <span className="inline-block text-xs font-semibold text-white bg-blue-600 px-2 py-1 rounded">
            {article.topic || 'Вести'}
          </span>
          <span className="inline-block text-xs font-semibold text-white bg-gray-500 px-2 py-1 rounded">
            {article.source}
          </span>
        </div>
        <h3 className="font-bold text-lg mb-2 line-clamp-2 hover:text-blue-600">
          {article.title}
        </h3>
        <p className="text-gray-600 text-sm line-clamp-2 mb-3">{article.description}</p>
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>👁️ {article.clicks} прегледи</span>
          <span>{new Date(article.created_at).toLocaleDateString('mk-MK')}</span>
        </div>
      </div>
    </article>
  );
};
