import React from 'react';
import { chooseClusterImage, buildProxySrcSet } from '../utils/imageSelection';
import { getDisplayTitle, getDisplaySummary, smartTruncate, isMostlyCyrillic, highlightScores, getDesignCardContext, slugify, transliterate, getSourceInitials } from '../utils/textUtils';
import { sanitizeHtml } from '../lib/sanitize';
import { dateLocaleForLang, localePathForLang } from '../lib/localePaths';
import { resolvePlaceholderTint } from '../lib/placeholderTheme';
import { buildPrimaryCardBadge, primaryCardBadgeTier } from '../lib/trustSignals';
import { useClientTranslations } from '../i18n/clientTranslations';
import { news } from '../i18n/namespaces/news';
import { cluster } from '../i18n/namespaces/cluster';
import { common } from '../i18n/namespaces/common';
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
  const t = useClientTranslations(locale, news, cluster, common);
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
  const cardSrcset = !isFallbackArt && thumbSrc ? buildProxySrcSet(thumbSrc, [360, 720, 1200]) : '';
  const tintColor = resolvePlaceholderTint(cluster.dominant_color);

  const rawLeadTitle = cluster.synthetic_headline || getDisplayTitle(main);
  let displayTitle = highlightScores(rawLeadTitle);
  if (locale === 'sr' && isMostlyCyrillic(displayTitle)) {
    displayTitle = highlightScores(transliterate(cluster.synthetic_headline || getDisplayTitle(main)));
  }
  const titleIsCyrillic = isMostlyCyrillic(displayTitle);

  const clusterSlug = slugify(cluster.synthetic_headline || getDisplayTitle(main));
  const clusterUrl = `${l('/cluster/')}${cluster.cluster_id}-${clusterSlug}`;

  const uniqueSources = Number((cluster as any).sources_count || (cluster as any).source_count || new Set(cluster.articles.map(a => a.source)).size);

  const trustInput = {
    sourcesCount: uniqueSources,
    pluralismScore: cluster.pluralism_score,
    isStale: false,
    hasVerification: Boolean(cluster.has_fact_check),
    quietFreshness: true,
    isPendingSynthesis: false,
    isProvisional: false,
    needsUpgrade: false,
  };
  const primaryCardBadge = buildPrimaryCardBadge(trustInput, locale);
  const primaryBadgeTier = primaryCardBadgeTier(trustInput);

  const hasPluralismConflict = (cluster.pluralism_score ?? 0) >= 55;

  const cardContext = getDesignCardContext(cluster);
  const cardLabel = cardContext.labelKey ? t(cardContext.labelKey as any) : '';
  const sourceInitials = getSourceInitials(main.source || '');
  const localizedTopic = cluster.topics?.[0] || main.topic || main.category || '';

  function getCardSummary(article: Article, lead = false) {
    const text = getDisplaySummary(article);
    if (!text) return '';
    const limit = lead ? 300 : 180;
    const truncated = smartTruncate(text, limit);
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

        {primaryCardBadge && variant !== 'wire' && variant !== 'compact' && (
          <div className="cluster-trust-row" aria-label={t('signal.cluster_row')}>
            <span className={`card-primary-badge card-primary-badge--${primaryBadgeTier}`} title={primaryCardBadge}>
              {primaryCardBadge}
            </span>
          </div>
        )}

        <div className="article-footer-meta mt-auto">
          <span className="time-stamp">{getTimeStr(main.ingested_at || main.created_at)}</span>
          {(variant === 'compact' || variant === 'wire') && primaryCardBadge && (
            <>
              <span className="meta-dot">·</span>
              <span className={`card-primary-badge card-primary-badge--${primaryBadgeTier} card-primary-badge--compact`}>
                {primaryCardBadge}
              </span>
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
                  srcSet={cardSrcset || undefined}
                  alt={displayTitle}
                  width="700"
                  height="500"
                  className="article-image w-full h-full object-cover rounded-md"
                  loading={isLead ? 'eager' : 'lazy'}
                  decoding="async"
                  data-fallback-url={fallbackImageUrl}
                  onLoad={(event) => {
                    const image = event.currentTarget;
                    image.classList.add('is-loaded');
                    const wrap = image.closest('.image-wrap');
                    if (wrap) {
                      wrap.setAttribute('data-image-state', 'ready');
                    }
                  }}
                  onError={(event) => {
                    const image = event.currentTarget;
                    image.onerror = null;
                    image.removeAttribute('srcset');
                    image.src = fallbackImageUrl;
                    image.classList.add('is-loaded', 'article-image-fallback');
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
