import React, { useState } from 'react';
import { NewsCard } from './NewsCard';

interface ArchiveFeedIslandProps {
  initialClusters: any[];
  initialHasMore: boolean;
  date: string;
  source: string;
  topic: string;
  pageSize: number;
}

const ArchiveFeedIsland: React.FC<ArchiveFeedIslandProps> = ({
  initialClusters,
  initialHasMore,
  date,
  source,
  topic,
  pageSize,
}) => {
  const [clusters, setClusters] = useState(initialClusters);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const loadMore = async () => {
    if (isLoading || !hasMore) return;
    setIsLoading(true);

    try {
      const nextPage = page + 1;
      const params = new URLSearchParams({
        date,
        page: String(nextPage),
        page_size: String(pageSize),
      });
      if (source) params.set('source', source);
      if (topic) params.set('topic', topic);

      const res = await fetch(`/api/archive?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        const newClusters = Array.isArray(data?.clusters) ? data.clusters : [];
        
        if (newClusters.length > 0) {
          setClusters((prev) => [...prev, ...newClusters]);
          setPage(nextPage);
          setHasMore(Boolean(data?.has_more));
        } else {
          setHasMore(false);
        }
      } else {
        console.error('Failed to fetch more clusters');
      }
    } catch (err) {
      console.error('Error loading more archive clusters:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="archive-feed-container">
      <div className="archive-clusters flex flex-col gap-6">
        {clusters.map((cluster: any, index: number) => (
          <div key={`${cluster.cluster_id}-${index}`} className="archive-cluster-row border-b border-border/50 pb-6 last:border-0">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="archive-cluster-index-col w-full md:w-20 pt-2 flex-shrink-0">
                <div className="sticky top-24 flex md:block items-baseline gap-2">
                  <span className="font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground block mb-1 hidden md:block">Архива</span>
                  <strong className="font-serif text-lg md:text-2xl font-black block leading-none opacity-40 md:opacity-100">{String(index + 1).padStart(2, '0')}</strong>
                  <span className="font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground md:hidden opacity-40">Позиција</span>
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <NewsCard cluster={cluster} variant={index < 4 ? 'featured' : 'compact'} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <div className="archive-load-more-wrap mt-10 text-center">
          <button
            onClick={loadMore}
            disabled={isLoading}
            className={`archive-page-link editorial-action px-8 py-3 border border-border inline-flex items-center gap-2 ${
              isLoading ? 'opacity-50 cursor-not-allowed' : 'hover:border-nyt-accent hover:text-nyt-accent'
            }`}
          >
            {isLoading ? (
              <>
                <span className="animate-spin">◌</span> Вчитување...
              </>
            ) : (
              'Вчитај повеќе'
            )}
          </button>
        </div>
      )}

      {!hasMore && clusters.length > 0 && (
        <p className="archive-end-note mt-12 text-center font-sans text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">
          Крај на архивата за овој ден
        </p>
      )}
    </div>
  );
};

export default ArchiveFeedIsland;
