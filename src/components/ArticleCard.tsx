import React from 'react';
import { ExternalLink, Clock } from 'lucide-react';
import { Article } from '../types';
import { apiClient } from '../api/client';

interface ArticleCardProps {
  article: Article;
  onClick?: () => void;
  compact?: boolean;
}

export const ArticleCard: React.FC<ArticleCardProps> = ({ article, onClick, compact = false }) => {
  const imageUrl = apiClient.getImageUrl(article.image_url, compact ? 160 : 400);

  if (compact) {
    return (
      <button
        onClick={onClick}
        className="w-full flex items-start gap-3 p-3 rounded-xl text-left hover:bg-surface-2 dark:hover:bg-dark-2 transition-colors group"
      >
        {imageUrl && (
          <div className="w-12 h-12 shrink-0 rounded-lg overflow-hidden bg-surface-3 dark:bg-dark-3">
            <img src={imageUrl} alt={article.title} className="w-full h-full object-cover" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium line-clamp-2 text-ink dark:text-slate-200 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors leading-snug">
            {article.title}
          </p>
          <div className="flex items-center gap-2 mt-1 text-xs text-ink-faint dark:text-slate-500">
            <span className="font-medium text-ink-muted dark:text-slate-400">{article.source}</span>
            {article.reading_time > 0 && (
              <>
                <span>·</span>
                <span className="flex items-center gap-0.5">
                  <Clock size={10} />
                  {article.reading_time} мин
                </span>
              </>
            )}
          </div>
        </div>
        <ExternalLink size={14} className="shrink-0 text-ink-faint dark:text-slate-600 mt-1" />
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className="w-full card overflow-hidden text-left group hover:shadow-card-hover transition-shadow"
    >
      {imageUrl && (
        <div className="relative w-full overflow-hidden bg-surface-3 dark:bg-dark-3" style={{ height: 160 }}>
          <img
            src={imageUrl}
            alt={article.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          {article.reading_time > 0 && (
            <span className="absolute bottom-2 right-2 flex items-center gap-1 bg-black/60 text-white text-xs px-2 py-0.5 rounded-full">
              <Clock size={10} />
              {article.reading_time} мин
            </span>
          )}
        </div>
      )}
      <div className="p-3">
        <div className="flex flex-wrap gap-1 mb-2">
          {article.topic && (
            <span className="badge-topic">{article.topic}</span>
          )}
          <span className="badge-source">{article.source}</span>
        </div>
        <h4 className="font-bold text-sm line-clamp-2 text-ink dark:text-slate-100 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors mb-1">
          {article.title}
        </h4>
        {article.description && (
          <p className="text-xs text-ink-muted dark:text-slate-400 line-clamp-2">{article.description}</p>
        )}
      </div>
    </button>
  );
};
