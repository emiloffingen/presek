import React, { useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useNewsStore } from '@/store/useNewsStore';
import { NewsCluster } from './NewsCluster';
import { Skeleton } from '../common/Skeleton';

export const NewsFeed: React.FC = () => {
  const { 
    clusters, page, hasMore, isFetching, fetchMore, trending,
    topic, query, isSaved
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
    <>
      <h1 className="visually-hidden">Најнови вести од Пресек</h1>
      <div id="newsFeed" className="news-feed-grid" aria-live="polite">
        {clusters.map((cluster, idx) => {
          const isLead = idx === 0 && !topic && !query && !isSaved;
          const showRibbon = idx === 3 && !topic && !query && !isSaved;
          return (
            <React.Fragment key={cluster.cluster_id}>
              <NewsCluster cluster={cluster} idx={idx} isLead={isLead} />
              {showRibbon && trending.length > 0 && (
                <div className="discovery-ribbon fade-in" style={{ gridColumn: '1 / -1' }}>
                  <div className="ribbon-title">Трендови во моментов</div>
                  <div className="ribbon-scroll">
                    {trending.slice(0, 10).map((t, i) => (
                      <Link key={i} to={`/?q=${encodeURIComponent(t.word)}`} className="ribbon-item">
                        <span className="src-badge">HOT</span>
                        <span className="ribbon-word">{t.word}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </React.Fragment>
          );
        })}
        
        {isFetching && <Skeleton count={3} />}
        
        {!isFetching && clusters.length === 0 && (
          <div className="error-state fade-in" style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1 / -1' }}>
            <p>Нема пронајдено вести за избраните критериуми.</p>
            <button className="cat-btn" style={{ marginTop: '1rem', background: 'var(--bg-elevated)' }} onClick={() => window.location.reload()}>Освежи</button>
          </div>
        )}

        <div ref={triggerRef} style={{ height: '20px', width: '100%', gridColumn: '1 / -1' }}></div>
      </div>
    </>
  );
};
