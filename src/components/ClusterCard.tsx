import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { NewsCluster } from '../types';
import { apiClient } from '../api/client';

interface ClusterCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  compact?: boolean;
}

function timeAgo(dateStr: string): string {
  try {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Тукушто';
    if (mins < 60) return `${mins}м`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}ч`;
    return `${Math.floor(hrs / 24)}д`;
  } catch {
    return '';
  }
}

export const ClusterCard: React.FC<ClusterCardProps> = ({ cluster, isLead, compact }) => {
  const navigate = useNavigate();
  const main = cluster.articles[0];
  
  const thumb = cluster.representative_image || cluster.articles.find(a => a.image_url)?.image_url;
  const thumbSrc = thumb ? apiClient.getImageUrl(thumb, isLead ? 1000 : 600) : null;

  const cardClass = isLead ? 'lead-story' : '';
  const thumbRight = !isLead && !compact; // Simplified logic for React version

  if (compact) {
    return (
      <article 
        onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
        className="news-cluster border-b border-color pb-4 cursor-pointer group"
      >
        <div className="flex justify-between items-start gap-3 mb-1">
          <span className="text-[10px] font-black uppercase text-accent">{main.source}</span>
          <span className="text-[10px] text-muted">{timeAgo(main.created_at)}</span>
        </div>
        <h3 className="font-serif font-bold text-sm text-primary group-hover:text-accent transition-colors leading-tight">
          {main.title}
        </h3>
      </article>
    );
  }

  return (
    <article 
      onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
      className={`news-cluster ${cardClass} fade-in cursor-pointer group`}
    >
      {thumbSrc && !thumbRight && (
        <div className="cluster-thumb-wrap">
          <img src={thumbSrc} alt="" className="cluster-thumb" loading={isLead ? 'eager' : 'lazy'} />
        </div>
      )}
      
      <div className="cluster-main">
        <div className="cluster-meta">
          <span className="text-accent">{main.source}</span>
          <span>·</span>
          <span>{timeAgo(main.created_at)}</span>
          {cluster.is_breaking && (
            <span className="breaking-dot" style={{ color: 'var(--accent-color)', fontWeight: 900, marginLeft: 4 }}>● LIVE</span>
          )}
        </div>

        <h2 className={`cluster-headline ${isLead ? 'text-2xl md:text-4xl' : 'text-lg'}`}>
          {main.title}
        </h2>
        
        {main.description && (
          <p className="cluster-excerpt">
            {main.description.length > (isLead ? 200 : 120) 
              ? main.description.substring(0, isLead ? 200 : 120) + '...' 
              : main.description}
          </p>
        )}
        
        {isLead && cluster.articles.length > 1 && (
          <div className="lead-sub-headlines mt-6 pt-4 border-t border-color space-y-3">
            {cluster.articles.slice(1, 4).map(sub => (
              <div key={sub.id} className="sub-h-item">
                <span className="text-[10px] font-black uppercase text-muted mr-2">{sub.source}:</span>
                <span className="font-serif font-bold text-sm text-primary hover:text-accent transition-colors leading-tight">
                  {sub.title}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="cluster-meta mt-auto pt-2">
          <span>{cluster.articles.length} извори анализирани</span>
        </div>
      </div>

      {thumbSrc && thumbRight && (
        <div className="cluster-thumb-wrap">
          <img src={thumbSrc} alt="" className="cluster-thumb" loading="lazy" />
        </div>
      )}
    </article>
  );
};
