import React from 'react';
import { ShieldCheck, Globe, CheckCircle2, Sparkles, Activity, Clock, Layers, Palette, ArrowRight } from 'lucide-react';
import { chooseClusterImage } from '../utils/imageSelection';
import { getDisplayTitle, getDisplaySummary, isMostlyCyrillic, highlightScores, getDesignCardContext } from '../utils/textUtils';
import { sanitizeHtml } from '../lib/sanitize';
import type { NewsCluster, Article } from '../types';

interface NewsCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  variant?: 'standard' | 'featured' | 'compact' | 'wire';
  lang?: string;
}

const _T: Record<string, Record<string, string>> = {
    'news.breaking': { sr: 'Široko pokriveno', mk: 'Широко покриено' },
    'news.tracked': { sr: 'Praćena tema', mk: 'Следена тема' },
    'news.urgent': { sr: 'Hitan razvoj', mk: 'Итен развој' },
    'news.ongoing': { sr: 'U toku', mk: 'Во тек' },
    'news.source': { sr: 'izvor', mk: 'извор' },
    'news.sources': { sr: 'izvora', mk: 'извори' },
    'news.synthesis': { sr: 'Sistemska sinteza Preseka', mk: 'Системска синтеза на Пресек' },
    'news.now': { sr: 'SADA', mk: 'СЕГА' },
    'news.ago': { sr: 'PRE', mk: 'ПРЕД' },
    'news.min_short': { sr: 'MIN', mk: 'МИН' },
    'news.go_to_article': { sr: 'IDI NA ČLANAK', mk: 'ОДИ ДО АРТИКЛОТ' },
    'news.global': { sr: 'SVETSKA vest', mk: 'СВЕТСКА вест' },
    'news.live': { sr: 'UŽIVO', mk: 'ВО ЖИВО' },
    'news.fact_check': { sr: 'FAKT-ČEK', mk: 'ФАКТ-ЧЕК' },
    'news.preview': { sr: 'PRESEK PREGLED', mk: 'ПРЕСЕК ПРЕГЛЕД' },
};

export const NewsCard: React.FC<NewsCardProps> = ({
  cluster,
  isLead = false,
  variant = 'standard',
  lang = 'sr'
}) => {
  const isMK = lang === 'mk';
  const t = (key: string) => _T[key]?.[lang] || key;

  const main = cluster.articles?.[0];
  if (!main) return null;

  const sourceSignal = main?.source_signal || {};
  const totalSources = cluster.articles.length;
  const showTrustBadge = totalSources >= 2 && Boolean(sourceSignal.trust_label);
  const showSignificanceLabel = cluster.is_breaking || totalSources >= 3;

  const significanceLabel =
    totalSources >= 6 ? t('news.breaking') :
    totalSources >= 4 ? t('news.tracked') :
    cluster.is_breaking ? t('news.urgent') :
    t('news.ongoing');

  const selectedImage = chooseClusterImage(cluster, isLead ? 'hero' : 'card');
  const thumbSrc = selectedImage.proxiedUrl;
  const isFallbackArt = selectedImage.isWeak;
  const tintColor = cluster.dominant_color || '#1e40af';

  const rawLeadTitle = cluster.synthetic_headline || getDisplayTitle(main);
  const displayTitle = highlightScores(rawLeadTitle);
  const titleIsCyrillic = isMostlyCyrillic(displayTitle);

  const cardContext = getDesignCardContext(cluster);
  // Simple mapping for card labels if needed, or just use defaults
  const cardLabel = t('news.preview');

  function getCardSummary(article: Article, lead = false) {
    const text = getDisplaySummary(article);
    if (!text) return '';
    const limit = lead ? 300 : 180;
    const truncated = text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text;
    return highlightScores(truncated);
  }

  const displaySummary = cluster.synthetic_standfirst || getCardSummary(main, isLead);
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

  return (
    <article className={`nyt-article variant-${variant} ${isLead ? 'lead-story' : ''} ${showTrustBadge ? 'premium-spotlight' : ''}`}>
      <div className="article-body">
        <div className="article-meta-v2">
          <div className="kicker-group min-w-0 flex flex-wrap items-center gap-1">
            <span className="kicker">{main.source}</span>
            {showTrustBadge && sourceSignal.trust_label === 'Visoko poverenje' && (
              <ShieldCheck size={10} className="text-blue-500" />
            )}
            {main.is_global && (
              <Globe size={10} className="text-emerald-500" />
            )}
          </div>

          <div className="meta-right">
            {showSignificanceLabel && (
                <span className={`significance-badge ${cluster.is_breaking ? 'is-breaking' : ''}`}>
                    {significanceLabel}
                </span>
            )}
            <span className="time-stamp">{getTimeStr(main.ingested_at || main.created_at)}</span>
          </div>
        </div>

        <a href={lang === 'sr' ? `/cluster/${cluster.cluster_id}` : `/mk/cluster/${cluster.cluster_id}`} className="headline-link group">
          <h2
            className={`headline ${
                isLead ? 'headline-lead' : (variant === 'compact' ? 'headline-compact' : 'headline-standard')
            } ${titleIsCyrillic ? 'headline-cyrillic' : ''} line-clamp-2 lg:line-clamp-3`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(displayTitle) }}
          ></h2>
        </a>

        {cluster.has_synthesis && (
            <span className="editorial-byline">
                <Sparkles size={11} className="inline-block mr-1 text-nyt-accent" />
                {t('news.synthesis')}
            </span>
        )}

        <div className="card-content-stack">
          {displaySummary && (
            <p
              className={`summary ${summaryIsCyrillic ? 'summary-cyrillic' : ''} min-w-0 break-words line-clamp-3 text-neutral-600 dark:text-neutral-400`}
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(displaySummary) }}
            ></p>
          )}
        </div>

        {isLead && cluster.articles.length > 1 && (
          <ul className="sub-headlines">
            {cluster.articles.slice(1, 4).map((sub: Article, idx: number) => (
              <li key={idx}>
                <a
                  href={lang === 'sr' ? `/cluster/${cluster.cluster_id}` : `/mk/cluster/${cluster.cluster_id}`}
                  dangerouslySetInnerHTML={{ __html: sanitizeHtml(getDisplayTitle(sub)) }}
                ></a>
              </li>
            ))}
          </ul>
        )}

        <div className="footer-meta flex items-center gap-[var(--grid-gap)] text-neutral-500 dark:text-neutral-400">
          <span className="flex items-center gap-1">
            <Clock size={11} />
            {getTimeStr(main.ingested_at || main.created_at)}
          </span>
          <span className="flex items-center gap-1">
            <Layers size={11} />
            {totalSources} {totalSources === 1 ? t('news.source') : t('news.sources')}
          </span>
        </div>
      </div>

      {thumbSrc && (
        <div className={`image-wrap ${isFallbackArt ? 'image-wrap-fallback' : ''}`}>
          <a href={lang === 'sr' ? `/cluster/${cluster.cluster_id}` : `/mk/cluster/${cluster.cluster_id}`} className="block h-full">
            {isFallbackArt ? (
              <div className="article-image-placeholder design-card" style={{ '--placeholder-bg': tintColor } as any}>
                <div className="design-card-pattern"></div>
                <div className="design-card-ribbon flex items-center justify-center text-center px-5 py-2 min-w-max">
                    <span>{cardLabel}</span>
                </div>
                <div className="design-card-main">
                    <div className="design-card-icon-wrap">
                        <Activity size={24} className="text-white/90" />
                    </div>
                    <h3 className={titleIsCyrillic ? 'headline-cyrillic' : ''}>{rawLeadTitle}</h3>
                    <p className="design-card-sub">{totalSources} {totalSources === 1 ? t('news.source') : t('news.sources')}</p>
                </div>
                <div className="design-card-footer">
                    <span className="design-card-cta">{t('news.go_to_article')} <ArrowRight size={12} className="ml-1" /></span>
                </div>
              </div>
            ) : (
              <div className="relative w-full h-full">
                <img
                  src={thumbSrc}
                  alt={displayTitle}
                  width="700"
                  height="500"
                  className="article-image is-loaded"
                  loading={isLead ? 'eager' : 'lazy'}
                />
              </div>
            )}
          </a>
          {isLead && main.image_caption && (
            <p className="image-caption">{main.image_caption}</p>
          )}
        </div>
      )}
    </article>
  );
};

function anyFactCheck(articles: Article[]) {
  return articles.some(a => a.is_fact_check);
}
