import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Flame, Sparkles, Clock, Layers } from 'lucide-react';
import { NewsCluster } from '../types';
import { apiClient } from '../api/client';

interface ClusterCardProps {
  cluster: NewsCluster;
  variant?: 'hero' | 'featured' | 'compact';
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Тукушто';
  if (mins < 60) return `${mins}м`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}ч`;
  return `${Math.floor(hrs / 24)}д`;
}

/* ── Hero Card (first story, full width) ───────────────────── */
function HeroCard({ cluster }: { cluster: NewsCluster }) {
  const navigate = useNavigate();
  const article = cluster.articles[0];
  const imageUrl = apiClient.getImageUrl(cluster.representative_image || article?.image_url, 900);

  return (
    <article
      onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
      className="relative w-full rounded-2xl overflow-hidden cursor-pointer group"
      style={{ minHeight: 480 }}
    >
      {/* Background image */}
      {imageUrl ? (
        <div className="absolute inset-0">
          <img
            src={imageUrl}
            alt=""
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
          <div className="absolute inset-0 img-overlay" />
        </div>
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-dark-0 to-dark-2" />
      )}

      {/* Content overlay */}
      <div className="relative z-10 flex flex-col justify-end h-full p-6 md:p-8" style={{ minHeight: 480 }}>
        {/* Badges */}
        <div className="flex flex-wrap gap-2 mb-3">
          {cluster.is_breaking && (
            <span className="badge-breaking flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-white breaking-dot" />
              BREAKING
            </span>
          )}
          {cluster.has_synthesis && (
            <span className="badge-synthesis flex items-center gap-1">
              <Sparkles size={11} />
              Синтеза
            </span>
          )}
          {article?.topic && (
            <span className="badge bg-white/20 text-white backdrop-blur-sm">
              {article.topic}
            </span>
          )}
        </div>

        {/* Title */}
        <h2 className="text-2xl md:text-3xl lg:text-4xl font-bold text-white leading-tight mb-2 group-hover:text-brand-200 transition-colors">
          {article?.title || 'Вести'}
        </h2>

        {/* Description */}
        {article?.description && (
          <p className="text-slate-300 text-sm md:text-base line-clamp-2 mb-3 max-w-2xl">
            {article.description}
          </p>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="flex items-center gap-1">
            <Layers size={12} />
            {cluster.articles.length} {cluster.articles.length === 1 ? 'извор' : 'извори'}
          </span>
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {timeAgo(article?.created_at || '')}
          </span>
          {cluster.articles.slice(0, 3).map((a) => (
            <span key={a.id} className="text-slate-500">
              {a.source}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}

/* ── Featured Card (medium, used in 2-col grid) ─────────────── */
function FeaturedCard({ cluster }: { cluster: NewsCluster }) {
  const navigate = useNavigate();
  const article = cluster.articles[0];
  const imageUrl = apiClient.getImageUrl(cluster.representative_image || article?.image_url, 600);

  return (
    <article
      onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
      className="card overflow-hidden cursor-pointer group flex flex-col"
    >
      {/* Image */}
      <div className="relative overflow-hidden bg-surface-3 dark:bg-dark-3" style={{ height: 200 }}>
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-dark-2 to-dark-0" />
        )}
        {cluster.is_breaking && (
          <span className="absolute top-2 left-2 badge-breaking flex items-center gap-1">
            <Flame size={11} />
            BREAKING
          </span>
        )}
        {cluster.has_synthesis && !cluster.is_breaking && (
          <span className="absolute top-2 left-2 badge-synthesis">
            <Sparkles size={11} className="mr-1" />
            Синтеза
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4">
        {article?.topic && (
          <span className="section-heading mb-1">{article.topic}</span>
        )}
        <h3 className="font-bold text-base leading-snug line-clamp-3 mb-2 text-ink dark:text-slate-100 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
          {article?.title}
        </h3>
        {article?.description && (
          <p className="text-sm text-ink-muted dark:text-slate-400 line-clamp-2 mb-3 flex-1">
            {article.description}
          </p>
        )}
        <div className="flex items-center justify-between text-xs text-ink-faint dark:text-slate-500 mt-auto">
          <span>{article?.source}</span>
          <span className="flex items-center gap-1">
            <Clock size={11} />
            {timeAgo(article?.created_at || '')}
            {cluster.articles.length > 1 && (
              <span className="ml-1 text-ink-faint dark:text-slate-500">
                · {cluster.articles.length} izvori
              </span>
            )}
          </span>
        </div>
      </div>
    </article>
  );
}

/* ── Compact Card (list item, no image) ─────────────────────── */
function CompactCard({ cluster }: { cluster: NewsCluster }) {
  const navigate = useNavigate();
  const article = cluster.articles[0];
  const imageUrl = apiClient.getImageUrl(cluster.representative_image || article?.image_url, 200);

  return (
    <article
      onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
      className="flex items-start gap-3 p-3 rounded-xl cursor-pointer group hover:bg-surface-2 dark:hover:bg-dark-2 transition-colors"
    >
      {/* Thumbnail */}
      {imageUrl && (
        <div className="w-16 h-16 shrink-0 rounded-lg overflow-hidden bg-surface-3 dark:bg-dark-3">
          <img src={imageUrl} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
        </div>
      )}

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm line-clamp-2 text-ink dark:text-slate-200 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors leading-snug">
          {article?.title}
        </p>
        <div className="flex items-center gap-2 mt-1 text-xs text-ink-faint dark:text-slate-500">
          {cluster.is_breaking && (
            <span className="text-brand-600 font-bold">BREAKING</span>
          )}
          <span>{article?.source}</span>
          <span>·</span>
          <span>{timeAgo(article?.created_at || '')}</span>
        </div>
      </div>
    </article>
  );
}

/* ── Export ──────────────────────────────────────────────────── */
export const ClusterCard: React.FC<ClusterCardProps> = ({ cluster, variant = 'featured' }) => {
  if (variant === 'hero') return <HeroCard cluster={cluster} />;
  if (variant === 'compact') return <CompactCard cluster={cluster} />;
  return <FeaturedCard cluster={cluster} />;
};
