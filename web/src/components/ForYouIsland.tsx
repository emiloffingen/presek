import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Clock3, Compass, Sparkles, AlertCircle, BrainCircuit } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  loadReaderProfile,
  loadSyncToken,
  recordSuggestionImpressions,
  sendSuggestionEvents,
  subscribeToReaderProfile,
} from '../lib/personalization.js';
import { cleanAndDecode, highlightScores } from '../utils/textUtils';

function getSummary(cluster: any) {
  const article = cluster?.articles?.[0];
  return cleanAndDecode(article?.summary || article?.description || '');
}

interface ForYouIslandProps {
  clusters?: any[];
  excludeClusterIds?: string[];
}

export default function ForYouIsland({ clusters = [], excludeClusterIds = [] }: ForYouIslandProps) {
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(() => loadReaderProfile());
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);

  // 1. Load Local Profile & Subscribe
  useEffect(() => {
    const unsubscribe = subscribeToReaderProfile((nextProfile) => {
      setProfile(nextProfile);
    });
    setLoading(false);
    return unsubscribe;
  }, []);

  // 2. Fetch Semantic Recommendations from API
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
            token: loadSyncToken(),
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
  }, [profile]);

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
    if (loading) return;
    
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
  }, [recommendations, loading]);

  if (loading) {
    return (
      <section className="for-you-module skeleton-fade" aria-busy="true" aria-label="Вчитување на персонализирани вести">
        <div className="for-you-head">
          <div>
            <div className="skeleton h-4 w-24 mb-2"></div>
            <div className="skeleton h-8 w-64"></div>
          </div>
        </div>
        <div className="for-you-grid">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="for-you-card">
              <div className="skeleton h-3 w-32 mb-4"></div>
              <div className="skeleton h-6 w-full mb-2"></div>
              <div className="skeleton h-6 w-3/4 mb-4"></div>
              <div className="skeleton h-4 w-full mb-1"></div>
              <div className="skeleton h-4 w-full mb-1"></div>
              <div className="skeleton h-4 w-1/2 mb-6"></div>
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
            <p className="for-you-kicker"><Sparkles size={14} /> За Вас</p>
            <h2 id="for-you-title">Персонализиран избор</h2>
          </div>
          <p className="for-you-note">
            Нашиот систем ја анализира вашата историја и наоѓа најрелевантни вести за вашите интереси.
          </p>
        </div>

        <div className="for-you-grid">
          {displayItems.map((item) => {
            const cluster = item.cluster || item; // Handle both Local (item.cluster) and Semantic (item itself) formats
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster);
            const isSemantic = Boolean(item.similarity);

            return (
              <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="for-you-card" aria-label={`Отвори кластер: ${cleanAndDecode(article.title)}`}>
                <p className={`for-you-card-kicker ${isSemantic ? 'text-nyt-accent' : ''}`}>
                  {isSemantic ? <BrainCircuit size={12} /> : <Compass size={12} />}
                  <span>{isSemantic ? 'Семантичка препорака' : (item.reason || 'Сродна тема')}</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: highlightScores(cleanAndDecode(article.title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'Извор'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} извори</span>
                  </div>
                  <span className="for-you-card-cta">Отвори <ArrowUpRight size={12} /></span>
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
          <p className="for-you-kicker"><Compass size={14} /> Откријте</p>
          <h2 id="discover-title">Најново за вас</h2>
        </div>
        <p className="for-you-note">
          Прилагодете го вашиот преглед со следење на теми и извори што ве интересираат.
        </p>
      </div>
      
      {fallbackItems.length > 0 ? (
        <div className="for-you-grid">
          {fallbackItems.map((cluster) => {
            const article = cluster.articles?.[0] || {};
            const summary = getSummary(cluster);
            return (
              <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="for-you-card" aria-label={`Отвори кластер: ${cleanAndDecode(article.title)}`}>
                <p className="for-you-card-kicker">
                  <Clock3 size={12} />
                  <span>Актуелно во моментот</span>
                </p>
                <h3 dangerouslySetInnerHTML={{ __html: highlightScores(cleanAndDecode(article.title)) }}></h3>
                {summary && <p className="for-you-card-copy">{summary}</p>}
                <div className="for-you-card-footer">
                  <div className="for-you-card-meta">
                    <span>{article.source || 'Извор'}</span>
                    <span>·</span>
                    <span>{cluster.sources_count ?? cluster.articles?.length ?? 0} извори</span>
                  </div>
                  <span className="for-you-card-cta">Отвори <ArrowUpRight size={12} /></span>
                </div>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="py-12 text-center border border-dashed border-border rounded-lg bg-secondary/5">
          <p className="text-sm text-muted-foreground">Нема нови препораки во овој момент.</p>
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
    <div className="for-you-follow-block" style={{ marginTop: '1.5rem', borderTop: '1px dashed var(--border)' }}>
      <div className="for-you-follow-head">
          <p className="for-you-kicker"><Sparkles size={14} /> Препорачано за следење</p>
      </div>
      <div className="for-you-follow-grid">
        {recommendations.topics.slice(0, 2).map((item: any) => (
          <div key={`topic:${item.value}`} className="for-you-follow-card">
            <div>
              <p className="for-you-follow-kicker">Тема</p>
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
              <p className="for-you-follow-kicker">Извор</p>
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
