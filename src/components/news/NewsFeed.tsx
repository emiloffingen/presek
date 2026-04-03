import React, { useEffect, useRef, useCallback } from 'react';
import { useNewsStore } from '@/store/useNewsStore';
import { NewsCluster } from './NewsCluster';
import { Skeleton } from '../common/Skeleton';

export const NewsFeed: React.FC = () => {
  const { 
    clusters, page, hasMore, isFetching, fetchMore
  } = useNewsStore();
  
  const observerRef = useRef<IntersectionObserver | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();
    
    observerRef.current = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !isFetching) {
        fetchMore();
      }
    }, { threshold: 0.1 });

    if (triggerRef.current) {
      observerRef.current.observe(triggerRef.current);
    }

    return () => observerRef.current?.disconnect();
  }, [fetchMore, hasMore, isFetching]);

  return (
    <div id="newsFeed" className="news-feed-grid" aria-live="polite">
      {clusters.map((cluster, idx) => (
        <NewsCluster key={cluster.cluster_id} cluster={cluster} idx={idx} page={page} />
      ))}
      
      {isFetching && <Skeleton count={3} />}
      
      {!isFetching && clusters.length === 0 && (
        <div className="error-state fade-in" style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <p>Нема пронајдено вести за избраните критериуми.</p>
          <button className="cat-btn" style={{ marginTop: '1rem', background: 'var(--bg-elevated)' }} onClick={() => window.location.reload()}>Освежи</button>
        </div>
      )}

      <div ref={triggerRef} style={{ height: '20px', width: '100%' }}></div>
    </div>
  );
};
