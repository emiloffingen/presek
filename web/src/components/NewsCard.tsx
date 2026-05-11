import React from 'react';
import { ShieldCheck, Globe, CheckCircle2, Sparkles, Activity } from 'lucide-react';
import { chooseClusterImage } from '../utils/imageSelection';
import { getDisplayTitle, getDisplaySummary, isMostlyCyrillic, highlightScores } from '../utils/textUtils';
import { sanitizeHtml } from '../lib/sanitize';
import type { NewsCluster, Article } from '../types';

interface NewsCardProps {
  cluster: NewsCluster;
  isLead?: boolean;
  variant?: 'standard' | 'featured' | 'compact' | 'wire';
}

export const NewsCard: React.FC<NewsCardProps> = ({
  cluster,
  isLead = false,
  variant = 'standard',
}) => {
  const main = cluster.articles?.[0];
  if (!main) return null;
  const sourceSignal = main?.source_signal || {};
  const sourceCount = cluster.articles.length;
  const showTrustBadge = sourceCount >= 2 && Boolean(sourceSignal.trust_label);
  const showSignificanceLabel = cluster.is_breaking || sourceCount >= 3;
  const significanceLabel =
    sourceCount >= 6
      ? 'Siroko pokrieno'
      : sourceCount >= 4
      ? 'Sledena tema'
      : cluster.is_breaking
      ? 'Iten razvoj'
      : 'Vo tek';

  const selectedImage = chooseClusterImage(cluster, isLead ? 'hero' : 'card');
  const thumbSrc = selectedImage.proxiedUrl;
  const isFallbackArt = selectedImage.isWeak;

  const displayTitle = highlightScores(getDisplayTitle(main));
  const titleIsCyrillic = isMostlyCyrillic(displayTitle);

  const getCardSummary = (article: Article, lead = false) => {
    const text = getDisplaySummary(article);
    if (!text) return '';
    const limit = lead ? 300 : 180;
    const truncated = text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text;
    return highlightScores(truncated);
  };

  const displaySummary = getCardSummary(main, isLead);
  const summaryIsCyrillic = isMostlyCyrillic(displaySummary);

  const getWhyItMatters = () => {
    if (sourceSignal.role_label && sourceCount >= 4) {
      return `${sourceSignal.role_label}. Temata vece se potvrduva i se prosiruva niz povece redakcii.`;
    }
    if (sourceSignal.role_label && sourceCount >= 2) {
      return `${sourceSignal.role_label}. Sledete me za novi potvrdi i reakcije.`;
    }
    if (sourceCount >= 6) {
      return `razvoj so siroko mediumsko pokrivanje od ${sourceCount} ${sourceCount === 1 ? 'izvor' : 'izvori'}.`;
    }
    if (sourceCount >= 4) {
      return 'Povece redakcii vece dodavaat novi detali.';
    }
    if (sourceCount >= 2) {
      return 'prica sto pocnuva da dobiva potvrdi i Siri kontekst.';
    }
    return 'Prv signal. Vredi da se sledi dali ce dobie posiroka potvrda.';
  };

  const whyItMatters = getWhyItMatters();

  const getTimeStr = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString('mk-RS', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <article className={`nyt-article variant-${variant} ${isLead ? 'lead-story' : ''}`}>
      <div className="article-body">
        <div className="article-meta">
          <span className="source-label">
            {main.source}
            {showTrustBadge && sourceSignal.trust_label === 'Visoko poverenje' && (
              <span title="Visoko poverenje">
                <ShieldCheck size={12} className="inline-block ml-1 text-blue-600 dark:text-blue-400" />
              </span>
            )}
          </span>

          {main.is_global && (
            <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-500">
              <Globe size={11} /> SVETSKA vest
            </span>
          )}

          {cluster.is_breaking && (

            <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-red-600 dark:text-red-500">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-600"></span>
              </span>
              VO ZIVO
            </span>
          )}

          {anyFactCheck(cluster.articles) && (
            <span className="bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-300 px-1.5 py-0.5 rounded text-[10px] font-bold border border-amber-200/50 flex items-center gap-1">
              FAKT-CEK
            </span>
          )}
        </div>


        <a href={`/cluster/${cluster.cluster_id}`} className="headline-link group">
          <h2
            className={`headline ${
                isLead ? 'headline-lead' : (variant === 'compact' ? 'headline-compact' : 'headline-standard')
            } ${titleIsCyrillic ? 'headline-cyrillic' : ''}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(displayTitle) }}
          ></h2>
        </a>

        {cluster.has_synthesis && (
            <span className="editorial-byline">
                <Sparkles size={11} className="inline-block mr-1 text-nyt-accent" />
                Sistemska sinteza na Presek
            </span>
        )}

        <div className="card-content-stack">
          {displaySummary && (
            <p
              className={`summary ${summaryIsCyrillic ? 'summary-cyrillic' : ''}`}
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(displaySummary) }}
            ></p>
          )}
        </div>

        {isLead && cluster.articles.length > 1 && (
          <ul className="sub-headlines">
            {cluster.articles.slice(1, 4).map((sub: Article, idx: number) => (
              <li key={idx}>
                <a
                  href={`/cluster/${cluster.cluster_id}`}
                  dangerouslySetInnerHTML={{ __html: sanitizeHtml(getDisplayTitle(sub)) }}
                ></a>
              </li>
            ))}
          </ul>
        )}

        <div className="footer-meta">
          <span>{getTimeStr(main.ingested_at || main.created_at)}</span>
          <span className="dot">·</span>
          <span>{cluster.articles.length} {cluster.articles.length === 1 ? 'izvor' : 'izvori'}</span>
        </div>
      </div>

      {thumbSrc && (
        <div className={`image-wrap ${isFallbackArt ? 'image-wrap-fallback' : ''}`}>
          <a href={`/cluster/${cluster.cluster_id}`} className="block h-full">
            {isFallbackArt ? (
              <div className="article-image-placeholder design-card">
                <div className="design-card-pattern"></div>
                <div className="design-card-ribbon">
                    <span>PRESEK PREGLED</span>
                </div>
                <div className="design-card-main">
                    <div className="design-card-icon-wrap">
                        <Activity size={24} className="text-white/90" />
                    </div>
                    <h3>{main.category || 'vesti'}</h3>
                    <p className="design-card-sub">{cluster.articles.length} {cluster.articles.length === 1 ? 'izvor' : 'izvori'}</p>
                </div>
                <div className="design-card-footer">
                    <span className="design-card-cta">ODI DO STATIJATA</span>
                </div>
              </div>
            ) : (
              <>
                <img
                  src={thumbSrc}
                  alt={displayTitle}
                  width="700"
                  height="500"
                  className="article-image"
                  loading={isLead ? 'eager' : 'lazy'}
                  onLoad={(e) => (e.currentTarget as HTMLImageElement).classList.add('is-loaded')}
                  onError={(e) => {
                    const img = e.currentTarget as HTMLImageElement;
                    img.style.display = 'none';
                    if (img.nextElementSibling) {
                      (img.nextElementSibling as HTMLElement).style.display = 'flex';
                    }
                  }}
                />
                <div className="article-image-placeholder design-card is-error-fallback" style={{ display: 'none' }}>
                    <div className="design-card-pattern"></div>
                    <div className="design-card-main">
                        <h3>{main.source}</h3>
                    </div>
                </div>
              </>
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
