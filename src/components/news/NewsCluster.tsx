import React from 'react';
import { Cluster } from '@/types';
import { clsx } from 'clsx';
import { Link } from 'react-router-dom';
import { Bookmark } from 'lucide-react';

interface NewsClusterProps {
  cluster: Cluster;
  idx: number;
  isLead: boolean;
}

export const NewsCluster: React.FC<NewsClusterProps> = ({ cluster, idx, isLead }) => {
  const articles = cluster.articles || [];
  const main = articles[0];
  const count = articles.length;
  
  // NYT Organic Grid Logic
  const isThumbRight = !isLead && (idx % 5 === 0);

  let thumbUrl = cluster.representative_image;
  if (!thumbUrl) {
    for (const a of articles) {
      if (a && a.image_url) {
        thumbUrl = a.image_url;
        break;
      }
    }
  }
  
  const thumbSrc = thumbUrl 
    ? (thumbUrl.startsWith('/') ? thumbUrl : `/proxy?url=${encodeURIComponent(thumbUrl)}`)
    : null;

  const handleImageError = (e: React.SyntheticEvent<HTMLImageElement, Event>) => {
    const img = e.currentTarget;
    if (thumbUrl && !img.src.includes(thumbUrl) && !thumbUrl.startsWith('/')) {
      // If proxy failed, try the original URL directly
      img.src = thumbUrl;
    } else {
      // If even original failed, hide the image container
      const wrap = img.closest('.cluster-thumb-wrap') as HTMLElement;
      if (wrap) wrap.style.display = 'none';
    }
  };

  const isBookmarked = false; // TODO: Implement bookmark state

  return (
    <article className={clsx(
      'news-cluster',
      isLead && 'lead-story',
      isThumbRight && 'thumb-right',
      'fade-in'
    )}>
      {thumbSrc && !isThumbRight && (
        <div className="cluster-thumb-wrap">
          <Link to={`/cluster/${cluster.cluster_id}`} style={{ display: 'block', width: '100%', height: '100%' }}>
            <img 
              src={thumbSrc} 
              alt={main.title} 
              className="cluster-thumb" 
              loading={idx < 3 ? 'eager' : 'lazy'} 
              onError={handleImageError}
            />
          </Link>
        </div>
      )}

      <div className="cluster-main">
        <Link to={`/cluster/${cluster.cluster_id}`} className="cluster-headline">
          {main.title}
        </Link>
        
        {(isLead || idx < 3) && main.description && (
          <p className="cluster-excerpt">
            {main.description.length > (isLead ? 220 : 120) 
              ? `${main.description.substring(0, isLead ? 220 : 120)}...` 
              : main.description}
          </p>
        )}

        {isLead && articles.length > 1 && (
          <div className="lead-sub-headlines">
            {articles.slice(1, 4).map((sub, sIdx) => (
              <div key={sIdx} className="sub-h-item">
                <span className="sub-h-source">{sub.source}:</span>
                <Link to={`/cluster/${cluster.cluster_id}`} className="sub-h-link">
                  {sub.title.length > 60 ? `${sub.title.substring(0, 60)}...` : sub.title}
                </Link>
              </div>
            ))}
          </div>
        )}

        <div className="cluster-meta">
          <span>{new Date(main.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}</span>
          <span>·</span>
          <span>{count} извори</span>
          <button className={clsx('bookmark-btn', isBookmarked && 'active')} style={{ marginLeft: 'auto' }}>
            <Bookmark size={14} fill={isBookmarked ? 'currentColor' : 'none'} />
          </button>
        </div>
      </div>

      {thumbSrc && isThumbRight && (
        <div className="cluster-thumb-wrap">
          <Link to={`/cluster/${cluster.cluster_id}`} style={{ display: 'block', width: '100%', height: '100%' }}>
            <img 
              src={thumbSrc} 
              alt={main.title} 
              className="cluster-thumb" 
              loading="lazy" 
              onError={handleImageError}
            />
          </Link>
        </div>
      )}
    </article>
  );
};
