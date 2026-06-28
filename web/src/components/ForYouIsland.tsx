import React, { useEffect, useMemo, useState, memo } from 'react';
import { ArrowUpRight, Clock3, Compass, Sparkles, BrainCircuit } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $syncToken } from '../lib/store.ts';
import PersonalizationWhyChip from './PersonalizationWhyChip.tsx';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildCsrfHeadersAsync,
  buildSurfaceFollowSuggestions,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { sanitizeHtml } from '../lib/sanitize';
import { localePathForLang, type Locale } from '../lib/localePaths';
import { useClientTranslations } from '../i18n/clientTranslations';
import { common } from '../i18n/namespaces/common';
import { getDisplayTitle, getStoryPreviewText, highlightScores, getPersonalizedText } from '../utils/textUtils';
import { PerformanceMonitor } from './PerformanceMonitor';

function getSummary(cluster: any, lang: string) {
  const article = cluster?.articles?.[0];
  const text = getStoryPreviewText(cluster, article, lang);
  return getPersonalizedText(text, lang);
}

function getTitle(cluster: any, lang: string) {
  const article = cluster?.articles?.[0];
  const text = cluster.synthetic_headline || getDisplayTitle(article, '', lang);
  return getPersonalizedText(text, lang);
}

interface ForYouIslandProps {
  clusters?: any[];
  excludeClusterIds?: string[];
  lang?: Locale;
}

function ForYouIslandComponent({ clusters = [], excludeClusterIds = [], lang = 'sr' }: ForYouIslandProps) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  
  // Performance monitoring - only in development
  const isDevelopment = process.env.NODE_ENV === 'development';
  isDevelopment && <PerformanceMonitor componentName="ForYouIsland" enabled={isDevelopment} />;
  const t = useClientTranslations(locale, common);
  const profile = useStore($profile);
  const syncToken = useStore($syncToken);

  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const activeProfile = isMounted ? profile : null;

  // Fetch Semantic Recommendations from API
  useEffect(() => {
    if (!isMounted) return;
    const hasSignals = hasPersonalizationSignal(profile);
    if (!hasSignals) return;

    const fetchSemantic = async () => {
      setSemanticLoading(true);
      try {
        const response = await fetch('/api/profile/sync/personalized-news', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(await buildCsrfHeadersAsync()) },
          body: JSON.stringify({
            token: syncToken,
            lang: lang,
            profile: profile
          }),
        });
        const data = await response.json();
        if (data.status === 'success' && data.results) {
          setSemanticResults(data.results);
        }
      } catch (e) {
        console.error('[Personalization] Semantic fetch failed:', e);
      } finally {
        setSemanticLoading(false);
      }
    };

    fetchSemantic();
  }, [profile, syncToken, lang]);

  const hasSignals = useMemo(() => {
    if (!isMounted) return false;
    return hasPersonalizationSignal(profile);
  }, [profile, isMounted]);

  // 3. Keyword-based Local Fallback (Personalization 1.0)
  const localPersonalizedItems = useMemo(() => {
    if (!hasSignals || !Array.isArray(clusters) || clusters.length === 0) return [];
    return buildPersonalizedClusters(clusters, profile, 4, excludeClusterIds, lang);
  }, [clusters, profile, hasSignals, excludeClusterIds, lang]);

  // 4. Combined Personalized Set
  // Priority: Semantic Results (Brain) > Local Matches (Keywords)
  const displayItems = useMemo(() => {
    const sortByBlend = (items: any[]) =>
      [...items].sort((left, right) => {
        const blendDelta = (Number(right.blend_score) || 0) - (Number(left.blend_score) || 0);
        if (blendDelta !== 0) return blendDelta;
        return (Number(right.profile_score) || 0) - (Number(left.profile_score) || 0);
      });
    if (semanticResults.length > 0) return sortByBlend(semanticResults);
    if (localPersonalizedItems.length > 0) return localPersonalizedItems;
    return [];
  }, [semanticResults, localPersonalizedItems]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(activeProfile, 'for_you', { topicLimit: 2, sourceLimit: 1, lang }),
    [activeProfile, lang]
  );

  const fallbackItems = useMemo(() => {
    if (displayItems.length > 0 || !Array.isArray(clusters)) return [];
    const excludeSet = new Set(excludeClusterIds);
    return clusters
      .filter(c => !excludeSet.has(c.cluster_id))
      .slice(0, 4);
  }, [clusters, displayItems.length, excludeClusterIds]);

  // Track impressions
  useEffect(() => {
    if (!isMounted) return;
    const suggestionList = [
      ...recommendations.topics.map((item) => ({ kind: 'topic' as const, value: item.value })),
      ...recommendations.sources.map((item) => ({ kind: 'source' as const, value: item.value })),
    ];

    if (suggestionList.length === 0) return;

    const result = recordSuggestionImpressions('for_you', suggestionList);
    if (result.recorded.length > 0) {
      sendSuggestionEvents(
        result.recorded.map((item) => ({
          surface: 'for_you',
          eventType: 'impression',
          suggestionKind: item.kind,
          value: item.value,
        }))
      );
    }
  }, [recommendations]);

  if (hasSignals && semanticLoading && displayItems.length === 0) {
    return (
      <section className="for-you-module" aria-labelledby="for-you-title">
        <div className="for-you-head">
          <div>
            <p className="for-you-kicker" aria-hidden="true"><Sparkles size={14} /> {t('for_you.hero_kicker')}</p>
            <h2 id="for-you-title" tabIndex="-1">{t('for_you.personalized_title')}</h2>
          </div>
          <p className="for-you-note" aria-live="polite">{t('for_you.preparing_recs')}</p>
        </div>
        <div className="for-you-grid">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="for-you-card border border-border bg-secondary/5 opacity-70">
              <div className="flex items-center gap-[var(--grid-gap)] mb-4 px-3 py-1 bg-secondary/20 rounded-full w-fit">
                <div className="w-3 h-3 rounded-full bg-secondary/40 animate-pulse"></div>
                <div className="h-2 w-20 bg-secondary/40 rounded animate-pulse"></div>
              </div>
              <div className="space-y-2 mb-4">
                <div className="h-3.5 w-full bg-secondary/30 rounded animate-pulse"></div>
                <div className="h-3.5 w-4/5 bg-secondary/30 rounded animate-pulse"></div>
              </div>
              <div className="space-y-1.5 mb-5">
                <div className="h-2 w-full bg-secondary/20 rounded animate-pulse delay-75"></div>
                <div className="h-2 w-5/6 bg-secondary/20 rounded animate-pulse delay-75"></div>
                <div className="h-2 w-4/6 bg-secondary/20 rounded animate-pulse delay-75"></div>
              </div>
              <div className="flex justify-between items-center mt-auto">
                <div className="flex gap-[var(--grid-gap)]">
                  <div className="h-2 w-12 bg-secondary/40 rounded animate-pulse delay-150"></div>
                  <div className="h-2 w-10 bg-secondary/40 rounded animate-pulse delay-150"></div>
                </div>
                <div className="h-2 w-10 bg-secondary/40 rounded animate-pulse delay-150"></div>
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  // Case 1: Has signals and found personalized content
  if (hasSignals && displayItems.length > 0) {
    return (
      <section className={`for-you-module ${semanticLoading ? 'opacity-70' : ''}`} aria-labelledby="for-you-title">
        <div className="for-you-head">
          <div>
            <p className="for-you-kicker" aria-hidden="true"><Sparkles size={14} /> {t('for_you.hero_kicker')}</p>
            <h2 id="for-you-title" tabIndex="-1">{t('for_you.personalized_title')}</h2>
          </div>
          <p className="for-you-note" aria-live="polite">{t('for_you.personalized_note')}</p>
        </div>

        <div className="for-you-grid">
          {displayItems.map((item) => {
            const cluster = item.cluster || item; // Handle both Local (item.cluster) and Semantic (item itself) formats
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster, lang);
            const title = getTitle(cluster, lang);
            const isSemantic = Boolean(item.similarity);
            const matchReasons = item.match_reasons || item.matchReasons || (item.reason ? [item.reason] : []);
            const whySummary = item.why_summary || item.whySummary || null;
            const sourceCount = cluster.sources_count ?? cluster.articles?.length ?? 0;

            return (
              <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, lang)} className={`for-you-card ${isSemantic ? 'premium-spotlight' : ''} focus-ring`} aria-label={t('for_you.open_story', { title })} tabIndex={0} role="article">
                <PersonalizationWhyChip
                  lang={lang}
                  reason={item.reason}
                  matchReasons={matchReasons}
                  matchedTopics={item.matched_topics || item.matchedTopics}
                  matchedSources={item.matched_sources || item.matchedSources}
                  whySummary={whySummary}
                />
                <p className={`for-you-card-kicker ${isSemantic ? 'text-presek-mark' : ''} flex items-center gap-[var(--grid-gap)] px-3 py-1 bg-secondary/10 rounded-full w-fit mb-4 min-w-max`}>
                  {isSemantic ? <BrainCircuit size={12} /> : <Compass size={12} />}
                  <span className="leading-none">{isSemantic ? t('for_you.semantic_rec') : (item.reason || t('for_you.related_topic'))}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || t('for_you.default_source')}</span>
                    <span>·</span>
                    <span>{sourceCount} {sourceCount === 1 ? t('for_you.sources_one') : t('for_you.sources_many')}</span>
                  </div>
                  <span className="for-you-card-cta">{t('for_you.context_open')} <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>

        <OnboardingIslandCompact profile={activeProfile} recommendations={recommendations} lang={lang} />
      </section>
    );
  }

  // Case 2: Fallback (No signals or no personalized items found)
  return (
    <section className="for-you-module" aria-labelledby="discover-title">
      <div className="for-you-head">
        <div>
          <p className="for-you-kicker"><Compass size={14} /> {t('for_you.discover_kicker_lower')}</p>
          <h2 id="discover-title">{t('for_you.seed_title')}</h2>
        </div>
        <p className="for-you-note">{t('for_you.seed_note')}</p>
      </div>

      {fallbackItems.length > 0 ? (
        <div className="for-you-grid">
          {fallbackItems.map((cluster) => {
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster, lang);
            const title = getTitle(cluster, lang);
            const sourceCount = cluster.sources_count ?? cluster.articles?.length ?? 0;
            return (
              <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, lang)} className="for-you-card focus-ring" aria-label={t('for_you.open_story', { title })} tabIndex={0} role="article">
                <p className="for-you-card-kicker flex items-center gap-[var(--grid-gap)] px-3 py-1 bg-secondary/10 rounded-full w-fit mb-4 min-w-max">
                  <Clock3 size={12} />
                  <span className="leading-none">{t('for_you.current_moment')}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || t('for_you.default_source')}</span>
                    <span>·</span>
                    <span>{sourceCount} {sourceCount === 1 ? t('for_you.sources_one') : t('for_you.sources_many')}</span>
                  </div>
                  <span className="for-you-card-cta">{t('for_you.context_open')} <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="py-12 text-center border border-dashed border-border rounded-none bg-secondary/5">
          <p className="text-sm text-muted-foreground">{t('for_you.no_new_recs')}</p>
        </div>
      )}

      <OnboardingIslandCompact profile={activeProfile} recommendations={recommendations} lang={lang} />
    </section>
  );
}

// Define when the component should update
const areEqual = (prevProps: ForYouIslandProps, nextProps: ForYouIslandProps) => {
  return (
    prevProps.clusters === nextProps.clusters &&
    prevProps.excludeClusterIds === nextProps.excludeClusterIds &&
    prevProps.lang === nextProps.lang
  );
};

// Memoize the component to prevent unnecessary re-renders
const ForYouIsland = memo(ForYouIslandComponent, areEqual);

ForYouIsland.displayName = 'ForYouIsland';

export default ForYouIsland;

function OnboardingIslandCompact({ profile, recommendations, lang = 'sr' }: any) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, common);
  if (((profile?.followedTopics || []).length + (profile?.followedSources || []).length >= 5)) return null;
  if (recommendations.topics.length === 0 && recommendations.sources.length === 0) return null;

  return (
    <div className="for-you-follow-block">
      <div className="for-you-follow-head">
          <p className="for-you-kicker"><Sparkles size={14} /> {t('for_you.follow_more')}</p>
      </div>
      <div className="for-you-follow-grid">
        {recommendations.topics.slice(0, 2).map((item: any) => (
          <div key={`topic:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">{t('for_you.kind_topic')}</p>
              <strong>{item.value}</strong>
              {item.reason && <p className="text-[10px] text-muted-foreground mt-1 opacity-80">{item.reason}</p>}
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              lang={lang}
              analyticsSurface="for_you"
            />
          </div>
        ))}
        {recommendations.sources.slice(0, 1).map((item: any) => (
          <div key={`source:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">{t('for_you.kind_source')}</p>
              <strong>{item.value}</strong>
              {item.reason && <p className="text-[10px] text-muted-foreground mt-1 opacity-80">{item.reason}</p>}
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              lang={lang}
              analyticsSurface="for_you"
            />
          </div>
        ))}
      </div>
    </div>
  );
}


