import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Sparkles } from 'lucide-react';
import { NewsCluster } from '../types';
import { apiClient } from '../api/client';

interface ClusterCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  compact?: boolean;
  reason?: string;
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

export const ClusterCard: React.FC<ClusterCardProps> = ({ cluster, isLead, compact, reason }) => {
  const navigate = useNavigate();
  const [imgFailed, setImgFailed] = React.useState(false);
  const main = cluster.articles[0];

  const rawThumb = cluster.representative_image || cluster.articles.find(a => a.image_url)?.image_url;
  // Treat the local placeholder as "no image" — it carries masthead text and looks terrible repeated.
  const thumb = rawThumb && !rawThumb.includes('placeholder') ? rawThumb : null;
  const thumbSrc = thumb && !imgFailed ? apiClient.getImageUrl(thumb, isLead ? 1000 : 600) : null;

  const cardClass = isLead ? 'lead-story' : '';
  const thumbRight = !isLead && !compact; // Simplified logic for React version

  if (compact) {
    return (
      <article 
        onClick={() => navigate(`/cluster/${cluster.cluster_id}`)}
        className="news-cluster border-b border-color pb-4 cursor-pointer group"
      >
        {reason && (
          <div className="flex items-center gap-1 mb-2 text-[9px] font-black uppercase text-accent">
            <Sparkles size={10} fill="currentColor" />
            {reason}
          </div>
        )}
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
      className={`news-cluster ${cardClass} animate-fade-in cursor-pointer group`}
    >
      {thumbSrc && !thumbRight && (
        <div className="cluster-thumb-wrap">
          <img src={thumbSrc} alt={main.title} className="cluster-thumb" loading={isLead ? 'eager' : 'lazy'} onError={() => setImgFailed(true)} />
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
          {cluster.has_synthesis && (
            <span className="text-[9px] font-black bg-accent text-white px-1 ml-2">СУБЛИМАТ</span>
          )}
          {cluster.has_fact_check && (
            <span className="text-[9px] font-black bg-blue-600 text-white px-1 ml-2">FACT CHECK</span>
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
          <img src={thumbSrc} alt={main.title} className="cluster-thumb" loading="lazy" />
        </div>
      )}
    </article>
  );
};
