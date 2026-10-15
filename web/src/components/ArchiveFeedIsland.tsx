import React, { useState } from 'react';
import { chooseClusterImage, buildProxySrcSet } from '../utils/imageSelection';
import { getDisplayTitle, slugify } from '../utils/textUtils';
import { dateLocaleForLang, localePathForLang } from '../lib/localePaths';
import { buildPrimaryCardBadge, primaryCardBadgeTier } from '../lib/trustSignals';
import { sectionLabelMk, sectionToneMk } from '../lib/broadsheetHome';
import { useClientTranslations } from '../i18n/clientTranslations';
import { archive } from '../i18n/namespaces/archive';
import { news } from '../i18n/namespaces/news';

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


const articleTime = (article: any, locale: string) => {
  const raw = article?.ingested_at || article?.created_at;
  if (!raw) return '';
  const date = new Date(String(raw).replace('Z', ''));
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(dateLocaleForLang(locale as any), { hour: '2-digit', minute: '2-digit' });
};

const ArchiveRow: React.FC<{ cluster: any; index: number; lead: boolean; locale: 'mk' | 'sr' }> = ({ cluster, index, lead, locale }) => {
  const main = cluster.articles?.[0];
  if (!main) return null;

  const title = String(cluster.synthetic_headline || getDisplayTitle(main) || '');
  const href = `${localePathForLang('/cluster/', locale)}${cluster.cluster_id}-${slugify(title)}`;
  const sources = Number(
    cluster.sources_count || cluster.source_count
    || new Set((cluster.articles || []).map((a: any) => a.source).filter(Boolean)).size,
  );
  const sectionRaw = main.subcategory || main.topic || main.category || '';
  const section = sectionLabelMk(sectionRaw) || '';
  const tone = sectionToneMk(sectionRaw) || undefined;

  const visual = chooseClusterImage(cluster, lead ? 'hero' : 'card', locale);
  const src = visual.proxiedUrl || visual.fallbackUrl;
  const srcSet = !visual.isWeak && visual.proxiedUrl
    ? buildProxySrcSet(visual.proxiedUrl, lead ? [480, 720, 960] : [160, 320])
    : undefined;

  const trustInput = {
    sourcesCount: sources,
    pluralismScore: cluster.pluralism_score,
    isStale: false,
    hasVerification: Boolean(cluster.has_fact_check),
    quietFreshness: true,
    isPendingSynthesis: false,
    isProvisional: false,
    needsUpgrade: false,
  };
  const badge = buildPrimaryCardBadge(trustInput, locale);
  const time = articleTime(main, locale);

  return (
    <article className={`ar-row${lead ? ' ar-row--lead' : ''}`} data-testid="archive-row">
      <span className="ar-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <div className="ar-body">
        <div className="ar-kicker">
          <span className="ar-index-inline" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
          <span className="ar-source">{main.source}</span>
          {section && <span className="ar-section" data-tone={tone}>{section}</span>}
        </div>
        <h2 className="ar-title"><a href={href}>{title}</a></h2>
        <div className="ar-meta">
          {sources > 0 && <span>{sources} {sources === 1 ? 'извор' : 'извори'}</span>}
          {time && <time dateTime={main.ingested_at || main.created_at}>{time}</time>}
          {badge && <span className={`ar-badge ar-badge--${primaryCardBadgeTier(trustInput)}`}>{badge}</span>}
        </div>
      </div>
      {src && (
        <a href={href} className="ar-photo" tabIndex={-1} aria-hidden="true">
          <img
            src={src}
            srcSet={srcSet}
            sizes={lead ? '(max-width: 759px) calc(100vw - 32px), 640px' : '112px'}
            alt=""
            loading={lead ? 'eager' : 'lazy'}
            decoding="async"
            onError={(event) => {
              const image = event.currentTarget;
              image.onerror = null;
              image.removeAttribute('srcset');
              if (visual.fallbackUrl && image.src !== visual.fallbackUrl) image.src = visual.fallbackUrl;
            }}
          />
        </a>
      )}
    </article>
  );
};

const ArchiveFeedIsland: React.FC<ArchiveFeedIslandProps> = ({
  initialClusters,
  initialHasMore,
  date,
  q,
  source,
  topic,
  pageSize,
  lang = 'mk'
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
  const t = useClientTranslations(activeLang, archive, news);

  return (
    <div className="archive-feed-container">
      <div className="archive-clusters ar-list">
        {clusters.map((cluster: any, index: number) => (
          <ArchiveRow
            key={`${cluster.cluster_id}-${index}`}
            cluster={cluster}
            index={index}
            lead={index === 0 && page === 0}
            locale={activeLang}
          />
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
