import React from 'react';
import { ShieldCheck, Globe, CheckCircle2, Activity, Clock, Layers, Palette, ArrowRight } from 'lucide-react';
import { chooseClusterImage } from '../utils/imageSelection';
import { getDisplayTitle, getDisplaySummary, isMostlyCyrillic, highlightScores, getDesignCardContext, slugify } from '../utils/textUtils';
import { sanitizeHtml } from '../lib/sanitize';
import { localePathForLang } from '../lib/localePaths';
import type { NewsCluster, Article } from '../types';

interface NewsCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  variant?: 'standard' | 'featured' | 'compact' | 'wire';
  lang?: string;
}

const _T: Record<string, Record<string, string>> = {
    'news.breaking': { sr: 'Udarna', mk: 'Ударна' },
    'news.tracked': { sr: 'Praćena', mk: 'Следена' },
    'news.urgent': { sr: 'Hitan razvoj', mk: 'Итен развој' },
    'news.ongoing': { sr: 'U toku', mk: 'Во тек' },
    'news.source': { sr: 'izvor', mk: 'извор' },
    'news.sources': { sr: 'izvora', mk: 'извори' },
    'news.synthesis': { sr: 'Sistemska sinteza Preseka', mk: 'Системска синтеза на Пресек' },
    'news.now': { sr: 'SADA', mk: 'СЕГА' },
    'news.just_now': { sr: 'UPRAVO SADA', mk: 'ТУКУШТО' },
    'news.ago': { sr: 'PRE', mk: 'ПРЕД' },
    'news.min_short': { sr: 'MIN', mk: 'МИН' },
    'news.go_to_article': { sr: 'ODI DO ČLANAK', mk: 'ОДИ ДО АРТИКЛОТ' },
    'news.global': { sr: 'SVETSKA vest', mk: 'СВЕТСКА вест' },
    'news.live': { sr: 'UŽIVO', mk: 'ВО ЖИВО' },
    'news.fact_check': { sr: 'FAKT-ČEK', mk: 'ФАКТ-ЧЕК' },
    'news.preview': { sr: 'PRESEK PREGLED', mk: 'ПРЕСЕК ПРЕГЛЕД' },
    'cluster.synthesis_badge': { sr: 'SINTEZA', mk: 'СИНТЕЗА' },
    'cluster.media_pluralism': { sr: 'MEDIJSKI PLURALIZAM', mk: 'МЕДИУМСКИ ПЛУРАЛИЗАМ' },
    'card.culture': { sr: 'KULTURNA PREPORUKA', mk: 'КУЛТУРНА ПРЕПОРАКА' },
    'card.politics': { sr: 'POLITIČKI FOKUS', mk: 'ПОЛИТИЧКИ ФОКУС' },
    'card.economy': { sr: 'EKONOMSKI BRIFING', mk: 'ЕКОНОМСКИ БРИФИНГ' },
    'card.sport': { sr: 'SPORTSKI PULS', mk: 'СПОРТСКИ ПУЛС' },
    'card.tech': { sr: 'TEHNOLOŠKI PRESEK', mk: 'ТЕХНОЛОШКИ ПРЕСЕК' },
    'card.general': { sr: 'SISTEMSKI PREGLED', mk: 'СИСТЕМСКИ ПРЕГЛЕД' },
};

export const NewsCard: React.FC<NewsCardProps> = ({
  cluster,
  isLead = false,
  variant = 'standard',
  lang = 'sr'
}) => {
  const t = (key: string) => _T[key]?.[lang] || key;
  const l = (path: string) => localePathForLang(path, lang as 'sr' | 'mk');

  const main = cluster.articles?.[0];
  if (!main) return null;

  const totalSources = Number((cluster as any).sources_count || (cluster as any).source_count || cluster.articles.length);
  const showSignificanceLabel = cluster.is_breaking || totalSources >= 3;

  const significanceLabel =
    totalSources >= 6 ? t('news.breaking') :
    totalSources >= 4 ? t('news.tracked') :
    cluster.is_breaking ? t('news.urgent') :
    t('news.ongoing');

  const selectedImage = chooseClusterImage(cluster, isLead ? 'hero' : 'card', lang as 'sr' | 'mk');
  const thumbSrc = selectedImage.proxiedUrl;
  const isFallbackArt = selectedImage.isWeak;
  const fallbackImageUrl = selectedImage.fallbackUrl;
  const tintColor = cluster.dominant_color || '#1e40af';

  const rawLeadTitle = cluster.synthetic_headline || getDisplayTitle(main);
  const displayTitle = highlightScores(rawLeadTitle);
  const titleIsCyrillic = isMostlyCyrillic(displayTitle);

  const clusterSlug = slugify(cluster.synthetic_headline || getDisplayTitle(main));
  const clusterUrl = `${l('/cluster/')}${cluster.cluster_id}-${clusterSlug}`;

  const uniqueSources = Number((cluster as any).sources_count || (cluster as any).source_count || new Set(cluster.articles.map(a => a.source)).size);
  
  const cardSignals = [
    cluster.pluralism_score != null ? `${t('cluster.media_pluralism')} ${cluster.pluralism_score}%` : '',
    cluster.pulse_score != null ? `PULSE ${cluster.pulse_score}%` : '',
    cluster.topics?.[0] || main.topic || main.category || '',
  ].filter(Boolean).slice(0, 2);

  const cardContext = getDesignCardContext(cluster);
  const cardLabel = cardContext.labelKey ? t(cardContext.labelKey) : '';

  function getCardSummary(article: Article, lead = false) {
    const text = getDisplaySummary(article);
    if (!text) return '';
    const limit = lead ? 300 : 180;
    const truncated = text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text;
    return highlightScores(truncated);
  }

  const displaySummary = getCardSummary(main, isLead);
  const summaryIsCyrillic = isMostlyCyrillic(displaySummary);

  const getTimeStr = (dateStr: string) => {
    try {
      const date = new Date(dateStr.replace("Z", ""));
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));

      if (diffMins < 1) return t('news.just_now');
      if (diffMins < 60) return `${t('news.ago')} ${diffMins} ${t('news.min_short')}`;
      return date.toLocaleTimeString(lang === 'sr' ? 'sr-RS' : 'mk-MK', {
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
      className={`nyt-article variant-${variant} ${isLead ? 'lead-story' : ''} ${thumbSrc ? 'has-image' : ''}`}
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

        {cardSignals.length > 0 && variant !== 'wire' && (
          <div className="cluster-signal-row" aria-label={lang === 'sr' ? 'Signali klastera' : 'Сигнали на кластерот'}>
            {cardSignals.map((signal, index) => (
              <span key={index}>{signal}</span>
            ))}
          </div>
        )}

        <div className="article-footer-meta mt-auto">
          <span className="time-stamp">{getTimeStr(main.ingested_at || main.created_at)}</span>
          <span className="meta-dot">·</span>
          <span className="source-count">{uniqueSources} {uniqueSources === 1 ? t('news.source') : t('news.sources')}</span>
        </div>
      </div>

      {thumbSrc && (
        <div 
          className={`image-wrap ${isFallbackArt ? 'image-wrap-fallback' : ''}`} 
          data-image-state={isFallbackArt ? 'fallback' : 'loading'}
          style={!isFallbackArt ? { '--placeholder-bg': tintColor } as any : undefined}
        >
          <a href={clusterUrl} className="block h-full" data-testid="cluster-link">
            {isFallbackArt ? (
              <div className="article-image-placeholder topic-fallback-card topic-fallback-card--proxy-only">
                <img
                  src={fallbackImageUrl}
                  alt=""
                  width="1200"
                  height="760"
                  className="article-image article-image-fallback is-loaded"
                  loading="lazy"
                  decoding="async"
                />
              </div>
            ) : (
              <div className="runtime-image-container relative w-full h-full">
                <img
                  src={thumbSrc}
                  alt={displayTitle}
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

function anyFactCheck(articles: Article[]) {
  return articles.some(a => a.is_fact_check);
}
