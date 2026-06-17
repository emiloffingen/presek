import React from 'react';
import { chooseClusterImage } from '../utils/imageSelection';
import { getDisplayTitle, getDisplaySummary, isMostlyCyrillic, highlightScores, getDesignCardContext, slugify, transliterate, getSourceInitials } from '../utils/textUtils';
import { sanitizeHtml } from '../lib/sanitize';
import { dateLocaleForLang, localePathForLang } from '../lib/localePaths';
import { getVisibleCardSignals, formatSignalBadge } from '../lib/signalBadges';
import { buildCompactPluralismMeta } from '../lib/trustSignals';
import { useTranslations } from '../i18n/utils';
import type { NewsCluster, Article } from '../types';

interface NewsCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  variant?: 'standard' | 'featured' | 'compact' | 'wire';
  lang?: string;
}

export const NewsCard: React.FC<NewsCardProps> = ({
  cluster,
  isLead = false,
  variant = 'standard',
  lang = 'sr'
}) => {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useTranslations(locale);
  const translate = (key: string, params?: Record<string, string | number>) => t(key as any, params);
  const l = (path: string) => localePathForLang(path, locale);

  const main = cluster.articles?.[0];
  if (!main) return null;

  const totalSources = Number((cluster as any).sources_count || (cluster as any).source_count || cluster.articles.length);
  const showSignificanceLabel = cluster.is_breaking || totalSources >= 3;

  const significanceLabel =
    totalSources >= 6 ? t('news.breaking') :
    totalSources >= 4 ? t('news.tracked') :
    cluster.is_breaking ? t('news.urgent') :
    t('news.ongoing');

  const selectedImage = chooseClusterImage(cluster, isLead ? 'hero' : 'card', locale);
  const thumbSrc = selectedImage.proxiedUrl;
  const isFallbackArt = selectedImage.isWeak;
  const fallbackImageUrl = selectedImage.fallbackUrl;
  const showMedia = Boolean(thumbSrc);
  const tintColor = cluster.dominant_color || '#1e40af';

  const rawLeadTitle = cluster.synthetic_headline || getDisplayTitle(main);
  let displayTitle = highlightScores(rawLeadTitle);
  if (locale === 'sr' && isMostlyCyrillic(displayTitle)) {
    displayTitle = highlightScores(transliterate(cluster.synthetic_headline || getDisplayTitle(main)));
  }
  const titleIsCyrillic = isMostlyCyrillic(displayTitle);

  const clusterSlug = slugify(cluster.synthetic_headline || getDisplayTitle(main));
  const clusterUrl = `${l('/cluster/')}${cluster.cluster_id}-${clusterSlug}`;

  const uniqueSources = Number((cluster as any).sources_count || (cluster as any).source_count || new Set(cluster.articles.map(a => a.source)).size);

  const signalBadges = getVisibleCardSignals({
    pluralismScore: cluster.pluralism_score,
    pulseScore: cluster.pulse_score,
    isBreaking: cluster.is_breaking,
    topic: cluster.topics?.[0] || main.topic || main.category || '',
  });
  const cardSignals = signalBadges.map((badge) =>
    formatSignalBadge(badge, locale, {
      pluralism: cluster.pluralism_score,
      pulse: cluster.pulse_score,
      topic: cluster.topics?.[0] || main.topic || main.category || '',
    }, translate),
  );

  const hasPluralismConflict = (cluster.pluralism_score ?? 0) >= 55;
  const compactPluralismMeta = (variant === 'compact' || variant === 'wire')
    ? buildCompactPluralismMeta({
        sourcesCount: uniqueSources,
        pluralismScore: cluster.pluralism_score,
      }, locale)
    : null;
  const conflictHeadlines = hasPluralismConflict
    ? Array.from(new Set(cluster.articles.slice(0, 3).map((article) => getDisplayTitle(article)).filter(Boolean)))
    : [];
  const showConflictPreview = conflictHeadlines.length >= 2;

  const cardContext = getDesignCardContext(cluster);
  const cardLabel = cardContext.labelKey ? t(cardContext.labelKey as any) : '';
  const sourceInitials = getSourceInitials(main.source || '');
  const localizedTopic = cluster.topics?.[0] || main.topic || main.category || '';

  function getCardSummary(article: Article, lead = false) {
    const text = getDisplaySummary(article);
    if (!text) return '';
    const limit = lead ? 300 : 180;
    const truncated = text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text;
    return highlightScores(truncated);
  }

  let displaySummary = getCardSummary(main, isLead);
  if (locale === 'sr' && isMostlyCyrillic(displaySummary)) {
    displaySummary = highlightScores(transliterate(displaySummary));
  }
  const summaryIsCyrillic = isMostlyCyrillic(displaySummary);

  const getTimeStr = (dateStr: string) => {
    try {
      const date = new Date(dateStr.replace("Z", ""));
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));

      if (diffMins < 1) return t('news.just_now');
      if (diffMins < 60) return `${t('news.ago')} ${diffMins} ${t('news.min_short')}`;
      return date.toLocaleTimeString(dateLocaleForLang(locale), {
          hour: '2-digit',
          minute: '2-digit'
      });
    } catch {
      return '';
    }
  };

  const slimCluster = {
    cluster_id: cluster.cluster_id,
    is_breaking: cluster.is_breaking,
    topics: cluster.topics,
    tags: cluster.tags,
    homepage_score: cluster.homepage_score,
    articles: cluster.articles.map((a, i) => (i === 0 ? {
      source: a.source,
      category: a.category,
      topic: a.topic,
    } : { source: a.source })),
  };

  return (
    <article 
      className={`nyt-article variant-${variant} ${isLead ? 'lead-story' : ''} ${showMedia ? 'has-image' : ''} ${showMedia && !isFallbackArt ? 'has-useful-image' : ''} ${showMedia && isFallbackArt ? 'has-editorial-fallback' : ''} ${hasPluralismConflict ? 'card-pluralism-conflict' : ''}`}
      data-cluster={JSON.stringify(slimCluster)}
      data-testid="article-card"
    >
      <div className="article-body">
        <div className="article-meta-v2">
          <div className="kicker-group">
            <span className="kicker">{main.source}</span>
            {cluster.is_breaking && (
              <span className="significance-badge is-breaking">{t('news.breaking').toUpperCase()}</span>
            )}
          </div>
        </div>

        <a href={clusterUrl} className="headline-link group" data-testid="cluster-link">
          <h2
            className={`headline ${
                isLead ? 'headline-lead' : (variant === 'compact' || variant === 'wire' ? 'headline-compact' : 'headline-standard')
            } ${titleIsCyrillic ? 'headline-cyrillic' : ''}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(displayTitle) }}
          ></h2>
        </a>

        {displaySummary && (
          <div className="card-content-stack">
            <p
              className={`summary ${summaryIsCyrillic ? 'summary-cyrillic' : ''}`}
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(displaySummary) }}
            ></p>
          </div>
        )}

        {cardSignals.length > 0 && variant !== 'wire' && variant !== 'compact' && (
          <div className="cluster-signal-row" aria-label={t('signal.cluster_row')}>
            <span>{cardSignals[0]}</span>
          </div>
        )}

        {showConflictPreview && (
          <div className="conflict-headline-preview" aria-label={t('pulse.conflict_angles')}>
            <p className="conflict-headline-kicker">{t('pulse.conflict_angles')}</p>
            {conflictHeadlines.slice(0, 2).map((headline, index) => (
              <p key={index} className="conflict-headline-variant">
                <strong>{t('pulse.conflict_headline')}:</strong> {headline}
              </p>
            ))}
          </div>
        )}

        <div className="article-footer-meta mt-auto">
          <span className="time-stamp">{getTimeStr(main.ingested_at || main.created_at)}</span>
          {compactPluralismMeta ? (
            <>
              <span className="meta-dot">·</span>
              <span className={`pluralism-meta${hasPluralismConflict ? ' pluralism-meta--conflict' : ''}`}>
                {compactPluralismMeta}
              </span>
            </>
          ) : (
            <>
              <span className="meta-dot">·</span>
              <span className="source-count">{uniqueSources} {uniqueSources === 1 ? t('news.source') : t('news.sources')}</span>
            </>
          )}
        </div>
      </div>

      {showMedia && (
        <div 
          className={`image-wrap ${isFallbackArt ? 'image-wrap-fallback' : ''}`} 
          data-image-state={isFallbackArt ? 'fallback' : 'loading'}
          data-fallback-source={main.source || ''}
          data-fallback-category={localizedTopic}
          data-fallback-tint={tintColor}
          data-fallback-label={cardLabel || localizedTopic || main.category || t('news.ongoing')}
          style={{ '--placeholder-bg': tintColor } as React.CSSProperties}
        >
          <a href={clusterUrl} className="block h-full" data-testid="cluster-link" tabIndex={-1} aria-hidden="true">
            {isFallbackArt ? (
              <div className={`article-image-placeholder topic-fallback-card topic-fallback-card--editorial${variant === 'compact' || variant === 'wire' ? ' topic-fallback-card--compact' : ''}`} style={{ '--placeholder-bg': tintColor } as React.CSSProperties}>
                <span className="article-image-placeholder-mark" aria-hidden="true">{sourceInitials}</span>
                <p className="article-image-placeholder-label">{cardLabel || localizedTopic || main.category || t('news.ongoing')}</p>
                <p className="article-image-placeholder-source">{main.source}</p>
              </div>
            ) : (
              <div className="runtime-image-container relative w-full h-full">
                <img
                  src={thumbSrc || undefined}
                  alt=""
                  width="700"
                  height="500"
                  className="article-image is-loaded w-full h-full object-cover rounded-md"
                  loading={isLead ? 'eager' : 'lazy'}
                  data-fallback-url={fallbackImageUrl}
                  onError={(event) => {
                    const image = event.currentTarget;
                    image.onerror = null;
                    image.removeAttribute('srcset');
                    image.src = fallbackImageUrl;
                    image.classList.add('article-image-fallback');
                    const wrap = image.closest('.image-wrap');
                    if (wrap) {
                      wrap.classList.add('image-wrap-fallback');
                      wrap.setAttribute('data-image-state', 'fallback');
                    }
                  }}
                />
              </div>
            )}
          </a>
        </div>
      )}
    </article>
  );
};
