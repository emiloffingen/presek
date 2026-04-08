import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Compass, Sparkles } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  loadReaderProfile,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { cleanAndDecode } from '../utils/textUtils';

function getSummary(cluster: any) {
  const article = cluster?.articles?.[0];
  return cleanAndDecode(article?.summary || article?.description || '');
}

export default function ForYouIsland({ clusters = [] }: { clusters?: any[] }) {
  const [items, setItems] = useState<any[]>([]);
  const [hasSignals, setHasSignals] = useState(false);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    // Small delay to simulate processing and prevent flicker
    const timer = setTimeout(() => {
      const profile = loadReaderProfile();
      setProfile(profile);
      const nextHasSignals = hasPersonalizationSignal(profile);
      setHasSignals(nextHasSignals);
      if (!nextHasSignals) {
        setItems([]);
      } else {
        setItems(buildPersonalizedClusters(clusters, profile, 4));
      }
      setLoading(false);
    }, 400);
    return () => clearTimeout(timer);
  }, [clusters]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'for_you', { topicLimit: 2, sourceLimit: 1 }),
    [profile]
  );

  useEffect(() => {
    if (loading || (recommendations.topics.length === 0 && recommendations.sources.length === 0)) return;
    const result = recordSuggestionImpressions('for_you', [
      ...recommendations.topics.map((item) => ({ kind: 'topic', value: item.value })),
      ...recommendations.sources.map((item) => ({ kind: 'source', value: item.value })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'for_you',
        eventType: 'impression',
        suggestionKind: item.kind,
        value: item.value,
      }))
    );
  }, [recommendations, loading]);

  if (loading) {
    return (
      <section className="for-you-module skeleton-fade">
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
              <div className="flex justify-between items-center">
                <div className="skeleton h-3 w-20"></div>
                <div className="skeleton h-3 w-16"></div>
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (!hasSignals || items.length === 0) {
    if (!recommendations.topics.length && !recommendations.sources.length) return null;
    
    return (
      <section className="for-you-module">
        <div className="for-you-head">
          <div>
            <p className="for-you-kicker"><Compass size={14} /> Откријте</p>
            <h2>Започнете го вашиот персонализиран тек</h2>
          </div>
          <p className="for-you-note">
            Следете ги темите што ве интересираат за да добивате препораки прилагодени на вашето читање.
          </p>
        </div>
        
        <div className="for-you-follow-grid" style={{ marginTop: '1rem' }}>
          {recommendations.topics.map((item) => (
            <div key={`topic:${item.value}`} className="for-you-follow-card">
              <div>
                <p className="for-you-follow-kicker">Препорачана Тема</p>
                <strong>{item.value}</strong>
                <p>{item.reason}</p>
              </div>
              <PreferenceToggle
                kind="topic"
                value={item.value}
                label={`тема: ${item.value}`}
                analyticsSurface="for_you"
                onChanged={() => setProfile(loadReaderProfile())}
              />
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="for-you-module">
      <div className="for-you-head">
        <div>
          <p className="for-you-kicker"><Sparkles size={14} /> За Вас</p>
          <h2>Патека според тоа што веќе следите</h2>
        </div>
        <p className="for-you-note">
          Избрано од вашите следени теми, омилени извори и неодамнешно читање на овој уред.
        </p>
      </div>

      <div className="for-you-grid">
        {items.map((item) => {
          const cluster = item.cluster;
          const article = cluster.articles?.[0] || {};
          const summary = getSummary(cluster);
          return (
            <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="for-you-card">
              <p className="for-you-card-kicker">
                <Compass size={12} />
                <span>{item.reason || 'Поврзано со вашето читање'}</span>
              </p>
              <h3>{cleanAndDecode(article.title) || 'Кластер'}</h3>
              {summary && <p className="for-you-card-copy">{summary}</p>}
              <div className="for-you-card-footer">
                <div className="for-you-card-meta">
                  <span>{article.source || 'Извор'}</span>
                  <span>·</span>
                  <span>{cluster.articles?.length || 0} извори</span>
                </div>
                <span className="for-you-card-cta">Отвори <ArrowUpRight size={12} /></span>
              </div>
            </a>
          );
        })}
      </div>

      {((profile?.followedTopics || []).length + (profile?.followedSources || []).length < 5) &&
        (recommendations.topics.length > 0 || recommendations.sources.length > 0) && (
        <div className="for-you-follow-block">
          <div className="for-you-follow-head">
            <p className="for-you-kicker"><Sparkles size={14} /> Следете го следното</p>
            <p className="for-you-note">
              Овие теми и извори се појавуваат во препораките што веќе ви одговараат.
            </p>
          </div>

          <div className="for-you-follow-grid">
            {recommendations.topics.map((item) => (
              <div key={`topic:${item.value}`} className="for-you-follow-card">
                <div>
                  <p className="for-you-follow-kicker">Тема</p>
                  <strong>{item.value}</strong>
                  <p>{item.reason}</p>
                </div>
                <PreferenceToggle
                  kind="topic"
                  value={item.value}
                  label={`тема: ${item.value}`}
                  analyticsSurface="for_you"
                  onChanged={() => setProfile(loadReaderProfile())}
                />
              </div>
            ))}

            {recommendations.sources.map((item) => (
              <div key={`source:${item.value}`} className="for-you-follow-card">
                <div>
                  <p className="for-you-follow-kicker">Извор</p>
                  <strong>{item.value}</strong>
                  <p>{item.reason}</p>
                </div>
                <PreferenceToggle
                  kind="source"
                  value={item.value}
                  label={`извор: ${item.value}`}
                  analyticsSurface="for_you"
                  onChanged={() => setProfile(loadReaderProfile())}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
