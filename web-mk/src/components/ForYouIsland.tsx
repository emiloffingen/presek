import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Clock3, Compass, Sparkles, BrainCircuit } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $syncToken } from '../lib/store.ts';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { sanitizeHtml } from '../lib/sanitize';
import { getDisplaySummary, getDisplayTitle, highlightScores } from '../utils/textUtils';

function getSummary(cluster: any) {
  const article = cluster?.articles?.[0];
  return getDisplaySummary(article);
}

function getTitle(cluster: any) {
  const article = cluster?.articles?.[0];
  return getDisplayTitle(article);
}

interface ForYouIslandProps {
  clusters?: any[];
  excludeClusterIds?: string[];
}

export default function ForYouIsland({ clusters = [], excludeClusterIds = [] }: ForYouIslandProps) {
  const profile = useStore($profile);
  const syncToken = useStore($syncToken);
  
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);

  // Fetch Semantic Recommendations from API
  useEffect(() => {
    const hasSignals = hasPersonalizationSignal(profile);
    if (!hasSignals) return;

    const fetchSemantic = async () => {
      setSemanticLoading(true);
      try {
        const response = await fetch('/api/profile/sync/personalized-news', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: syncToken,
            profile: profile
          })
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
  }, [profile, syncToken]);

  const hasSignals = useMemo(() => hasPersonalizationSignal(profile), [profile]);

  // 3. Keyword-based Local Fallback (Personalization 1.0)
  const localPersonalizedItems = useMemo(() => {
    if (!hasSignals || !Array.isArray(clusters) || clusters.length === 0) return [];
    return buildPersonalizedClusters(clusters, profile, 4, excludeClusterIds);
  }, [clusters, profile, hasSignals, excludeClusterIds]);

  // 4. Combined Personalized Set
  // Priority: Semantic Results (Brain) > Local Matches (Keywords)
  const displayItems = useMemo(() => {
    if (semanticResults.length > 0) return semanticResults;
    if (localPersonalizedItems.length > 0) return localPersonalizedItems;
    return [];
  }, [semanticResults, localPersonalizedItems]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'for_you', { topicLimit: 2, sourceLimit: 1 }),
    [profile]
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
            <p className="for-you-kicker"><Sparkles size={14} /> За Вас</p>
            <h2 id="for-you-title">Персонализиран избор</h2>
          </div>
          <p className="for-you-note">Подготвување препораки...</p>
        </div>
        <div className="for-you-grid">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="for-you-card border border-border bg-secondary/5 opacity-70">
              <div className="flex items-center gap-2 mb-3">
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
                <div className="flex gap-2">
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
            <p className="for-you-kicker"><Sparkles size={14} /> Za Vas</p>
            <h2 id="for-you-title">Personaliziran izbor</h2>
          </div>
          <p className="for-you-note">
            Izbor spored temite i izvorite sto vece im sledite.
          </p>
        </div>

        <div className="for-you-grid">
          {displayItems.map((item) => {
            const cluster = item.cluster || item; // Handle both Local (item.cluster) and Semantic (item itself) formats
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster);
            const title = getTitle(cluster);
            const isSemantic = Boolean(item.similarity);

            return (
              <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className={`for-you-card ${isSemantic ? 'premium-spotlight' : ''}`} aria-label={`Otvori klaster: ${title}`}>
                <p className={`for-you-card-kicker ${isSemantic ? 'text-nyt-accent' : ''}`}>
                  {isSemantic ? <BrainCircuit size={12} /> : <Compass size={12} />}
                  <span>{isSemantic ? 'Semanticka preporaka' : (item.reason || 'Srodna tema')}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'izvor'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} { (cluster.sources_count ?? cluster.articles?.length ?? 0) === 1 ? 'izvor' : 'izvori' }</span>
                  </div>
                  <span className="for-you-card-cta">Otvori <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>
        
        <OnboardingIslandCompact profile={profile} recommendations={recommendations} />
      </section>
    );
  }

  // Case 2: Fallback (No signals or no personalized items found)
  return (
    <section className="for-you-module" aria-labelledby="discover-title">
      <div className="for-you-head">
        <div>
          <p className="for-you-kicker"><Compass size={14} /> Otkrijte</p>
          <h2 id="discover-title">Najnovo za vas</h2>
        </div>
        <p className="for-you-note">
          Poceten izbor dodeka ne postavite sto sakate da sledite.
        </p>
      </div>
      
      {fallbackItems.length > 0 ? (
        <div className="for-you-grid">
          {fallbackItems.map((cluster) => {
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster);
            const title = getTitle(cluster);
            return (
              <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="for-you-card" aria-label={`Otvori klaster: ${title}`}>
                <p className="for-you-card-kicker">
                  <Clock3 size={12} />
                  <span>Актуелно во моментот</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: sanitizeHtml(highlightScores(title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'izvor'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} { (cluster.sources_count ?? cluster.articles?.length ?? 0) === 1 ? 'izvor' : 'izvori' }</span>
                  </div>
                  <span className="for-you-card-cta">Otvori <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="py-12 text-center border border-dashed border-border rounded-lg bg-secondary/5">
          <p className="text-sm text-muted-foreground">Nema novi preporaki vo ovoj moment.</p>
        </div>
      )}

      <OnboardingIslandCompact profile={profile} recommendations={recommendations} />
    </section>
  );
}

function OnboardingIslandCompact({ profile, recommendations }: any) {
  if (((profile?.followedTopics || []).length + (profile?.followedSources || []).length >= 5)) return null;
  if (recommendations.topics.length === 0 && recommendations.sources.length === 0) return null;

  return (
    <div className="for-you-follow-block">
      <div className="for-you-follow-head">
          <p className="for-you-kicker"><Sparkles size={14} /> Sledete dalje</p>
      </div>
      <div className="for-you-follow-grid">
        {recommendations.topics.slice(0, 2).map((item: any) => (
          <div key={`topic:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">Tema</p>
              <strong>{item.value}</strong>
              {item.reason && <p className="text-[10px] text-muted-foreground mt-1 opacity-80">{item.reason}</p>}
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              analyticsSurface="for_you"
            />
          </div>
        ))}
        {recommendations.sources.slice(0, 1).map((item: any) => (
          <div key={`source:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">извор</p>
              <strong>{item.value}</strong>
              {item.reason && <p className="text-[10px] text-muted-foreground mt-1 opacity-80">{item.reason}</p>}
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              analyticsSurface="for_you"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
