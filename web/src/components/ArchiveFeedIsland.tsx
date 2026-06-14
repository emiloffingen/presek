import React, { useState } from 'react';
import { NewsCard } from './NewsCard';
import { useTranslations } from '../i18n/utils';

interface ArchiveFeedIslandProps {
  initialClusters: any[];
  initialHasMore: boolean;
  date: string;
  q: string;
  source: string;
  topic: string;
  pageSize: number;
  lang?: string;
}

const ArchiveFeedIsland: React.FC<ArchiveFeedIslandProps> = ({
  initialClusters,
  initialHasMore,
  date,
  q,
  source,
  topic,
  pageSize,
  lang = 'sr'
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
        lang: lang,
      });
      if (q) params.set('q', q);
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

  const SkeletonCard = () => (
    <div className="animate-pulse flex flex-col gap-[var(--grid-gap)]">
        <div className="flex items-center gap-[var(--grid-gap)]">
            <div className="h-2 w-16 bg-muted rounded"></div>
            <div className="h-2 w-24 bg-muted rounded opacity-50"></div>
        </div>
        <div className="h-6 w-3/4 bg-muted rounded"></div>
        <div className="h-4 w-1/2 bg-muted rounded opacity-70"></div>
        <div className="flex gap-[var(--grid-gap)] mt-2">
            <div className="h-24 w-full bg-muted rounded opacity-30"></div>
        </div>
    </div>
  );

  const activeLang = lang === 'mk' ? 'mk' : 'sr';
  const t = useTranslations(activeLang);

  return (
    <div className="archive-feed-container">
      <div className="archive-clusters flex flex-col gap-6 md:gap-10">
        {clusters.map((cluster: any, index: number) => (
          <div key={`${cluster.cluster_id}-${index}`} className="archive-cluster-row border-b border-foreground/5 pb-6 md:pb-10 last:border-0">
            <div className="flex flex-col md:flex-row gap-3 md:gap-[var(--grid-gap)]">
              <div className="archive-cluster-index-col w-full md:w-20 pt-1 md:pt-2 flex-shrink-0">
                <div className="sticky top-24 flex md:block items-baseline gap-2 md:gap-[var(--grid-gap)]">
                  <span className="font-sans text-[10px] font-black uppercase tracking-widest text-nyt-accent block mb-1 hidden md:block">{t('archive.edition')}</span>
                  <strong className="font-serif text-base md:text-3xl font-black block leading-none opacity-20 md:opacity-40">{String(index + 1).padStart(2, '0')}</strong>
                  <span className="font-sans text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground md:hidden opacity-40">{t('archive.pos')}</span>
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <NewsCard cluster={cluster} variant={index === 0 && page === 0 ? 'featured' : 'compact'} lang={lang} />
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
            <div className="flex flex-col gap-6 md:gap-10 opacity-50">
                {[1, 2, 3].map(i => (
                    <div key={i} className="flex flex-col md:flex-row gap-3 md:gap-[var(--grid-gap)] border-b border-foreground/5 pb-6 md:pb-10">
                        <div className="w-20 shrink-0">
                             <div className="h-8 w-12 bg-muted rounded"></div>
                        </div>
                        <div className="flex-1"><SkeletonCard /></div>
                    </div>
                ))}
            </div>
        )}
      </div>

      {hasMore && !isLoading && (
        <div className="archive-load-more-wrap mt-10 md:mt-16 text-center border-t border-foreground pt-6 md:pt-10">
          <button
            onClick={loadMore}
            className="archive-page-link editorial-action px-8 md:px-12 py-3 md:py-4 border border-foreground font-sans text-[11px] md:text-xs font-black uppercase tracking-[0.14em] md:tracking-widest hover:bg-foreground hover:text-background transition-colors"
          >
            {t('archive.load_more')}
          </button>
        </div>
      )}

      {!hasMore && clusters.length > 0 && (
        <p className="archive-end-note mt-8 md:mt-12 text-center font-sans text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest text-muted-foreground opacity-60">
          {t('archive.end')}
        </p>
      )}
    </div>
  );
};

export default ArchiveFeedIsland;
