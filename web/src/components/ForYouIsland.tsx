import React, { useEffect, useMemo, useState } from 'react';
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
import { useTranslations } from '../i18n/utils';
import { getDisplayTitle, getStoryPreviewText, highlightScores, getPersonalizedText } from '../utils/textUtils';

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

export default function ForYouIsland({ clusters = [], excludeClusterIds = [], lang = 'sr' }: ForYouIslandProps) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useTranslations(locale);
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
    if (semanticResults.length > 0) return semanticResults;
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
            <p className="for-you-kicker"><Sparkles size={14} /> {lang === 'sr' ? 'Za Vas' : 'За Вас'}</p>
            <h2 id="for-you-title">{lang === 'sr' ? 'Personalizovan izbor' : 'Персонализиран избор'}</h2>
          </div>
          <p className="for-you-note">{lang === 'sr' ? 'Pripremanje preporuka...' : 'Подготовка на препораки...'}</p>
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
            <p className="for-you-kicker"><Sparkles size={14} /> {lang === 'sr' ? 'Za Vas' : 'За Вас'}</p>
            <h2 id="for-you-title">{lang === 'sr' ? 'Personalizovan izbor' : 'Персонализиран избор'}</h2>
          </div>
          <p className="for-you-note">
            {lang === 'sr' ? 'Izbor prema temama i izvorima koje najviše pratite.' : 'Избор според темите и изворите што најмногу ги следите.'}
          </p>
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

            return (
              <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, lang)} className={`for-you-card ${isSemantic ? 'premium-spotlight' : ''}`} aria-label={t('for_you.open_story', { title })}>
                <PersonalizationWhyChip
                  lang={lang}
                  reason={item.reason}
                  matchReasons={matchReasons}
                  matchedTopics={item.matched_topics || item.matchedTopics}
                  matchedSources={item.matched_sources || item.matchedSources}
                  whySummary={whySummary}
                />
                <p className={`for-you-card-kicker ${isSemantic ? 'text-nyt-accent' : ''} flex items-center gap-[var(--grid-gap)] px-3 py-1 bg-secondary/10 rounded-full w-fit mb-4 min-w-max`}>
                  {isSemantic ? <BrainCircuit size={12} /> : <Compass size={12} />}
                  <span className="leading-none">{isSemantic ? (lang === 'sr' ? 'Semantička preporuka' : 'Семантичка препорака') : (item.reason || (lang === 'sr' ? 'Srodna tema' : 'Сродна тема'))}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'izvor'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} { (cluster.sources_count ?? cluster.articles?.length ?? 0) === 1 ? (lang === 'sr' ? 'izvor' : 'извор') : (lang === 'sr' ? 'izvora' : 'извори') }</span>
                  </div>
                  <span className="for-you-card-cta">{lang === 'sr' ? 'Otvori' : 'Отвори'} <ArrowUpRight size={12} /></span>
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
          <p className="for-you-kicker"><Compass size={14} /> {lang === 'sr' ? 'Za vas' : 'За вас'}</p>
          <h2 id="discover-title">{lang === 'sr' ? 'Početne preporuke' : 'Почетни препораки'}</h2>
        </div>
        <p className="for-you-note">
          {lang === 'sr'
            ? 'Izbor po vašim temama dok ne pratite izvore. Ovo nije naslovna priča.'
            : 'Избор по вашите теми додека не следите извори. Ова не е насловна приказна.'}
        </p>
      </div>

      {fallbackItems.length > 0 ? (
        <div className="for-you-grid">
          {fallbackItems.map((cluster) => {
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster, lang);
            const title = getTitle(cluster, lang);
            return (
              <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, lang)} className="for-you-card" aria-label={t('for_you.open_story', { title })}>
                <p className="for-you-card-kicker flex items-center gap-[var(--grid-gap)] px-3 py-1 bg-secondary/10 rounded-full w-fit mb-4 min-w-max">
                  <Clock3 size={12} />
                  <span className="leading-none">{lang === 'sr' ? 'Aktuelno u trenutku' : 'Актуелно во моментот'}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'izvor'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} { (cluster.sources_count ?? cluster.articles?.length ?? 0) === 1 ? (lang === 'sr' ? 'izvor' : 'извор') : (lang === 'sr' ? 'izvora' : 'извори') }</span>
                  </div>
                  <span className="for-you-card-cta">{lang === 'sr' ? 'Otvori' : 'Отвори'} <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="py-12 text-center border border-dashed border-border rounded-lg bg-secondary/5">
          <p className="text-sm text-muted-foreground">{lang === 'sr' ? 'Nema novih preporuka u ovom trenutku.' : 'Нема нови препораки во овој момент.'}</p>
        </div>
      )}

      <OnboardingIslandCompact profile={activeProfile} recommendations={recommendations} lang={lang} />
    </section>
  );
}

function OnboardingIslandCompact({ profile, recommendations, lang = 'sr' }: any) {
  if (((profile?.followedTopics || []).length + (profile?.followedSources || []).length >= 5)) return null;
  if (recommendations.topics.length === 0 && recommendations.sources.length === 0) return null;

  return (
    <div className="for-you-follow-block">
      <div className="for-you-follow-head">
          <p className="for-you-kicker"><Sparkles size={14} /> {lang === 'sr' ? 'Pratite dalje' : 'Следете понатаму'}</p>
      </div>
      <div className="for-you-follow-grid">
        {recommendations.topics.slice(0, 2).map((item: any) => (
          <div key={`topic:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">{lang === 'sr' ? 'Tema' : 'Тема'}</p>
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
              <p className="for-you-follow-kicker">{lang === 'sr' ? 'Izvor' : 'Извор'}</p>
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
