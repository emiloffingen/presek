import React, { useEffect, useMemo } from 'react';
import { Sparkles } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile } from '../lib/store.ts';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';

type Suggestion = {
  value: string;
  reason: string;
};

export default function ClusterFollowSuggestionsIsland({
  topic = '',
  source = '',
  adjacentTopic = '',
  lang = 'sr'
}: {
  topic?: string;
  source?: string;
  adjacentTopic?: string;
  lang?: string;
}) {
  const profile = useStore($profile);
  const isMK = lang === 'mk';

  const suggestions = useMemo(() => {
    const base = buildSurfaceFollowSuggestions(profile, 'cluster', { topicLimit: 2, sourceLimit: 1 });
    const followedTopics = new Set(profile?.followedTopics || []);
    const followedSources = new Set(profile?.followedSources || []);

    const topicSuggestions: Suggestion[] = [...base.topics];
    const sourceSuggestions: Suggestion[] = [...base.sources];

    const addUnique = (list: Suggestion[], item: Suggestion, existing: Set<string>) => {
      if (!item.value || existing.has(item.value) || list.some((entry) => entry.value === item.value)) return;
      list.unshift(item);
    };

    addUnique(topicSuggestions, {
      value: String(topic || '').trim(),
      reason: isMK ? 'ова е главната тема на кластерот што го читате.' : 'ovo je glavna tema klastera koji čitate.',
    }, followedTopics);
    
    if (adjacentTopic) {
        addUnique(topicSuggestions, {
          value: String(adjacentTopic || '').trim(),
          reason: isMK ? 'оваа поврзана тема често ја носи следната развојна линија.' : 'ova povezana tema često nosi sledeću razvojnu liniju.',
        }, followedTopics);
    }
    
    addUnique(sourceSuggestions, {
      value: String(source || '').trim(),
      reason: isMK ? 'овој извор ја води главната линија во кластерот што го читате.' : 'ovaj izvor vodi glavnu liniju u klasteru koji čitate.',
    }, followedSources);

    return {
      topics: topicSuggestions.slice(0, 2),
      sources: sourceSuggestions.slice(0, 2),
    };
  }, [profile, topic, source, adjacentTopic, isMK]);

  useEffect(() => {
    const result = recordSuggestionImpressions('cluster', [
      ...suggestions.topics.map((item) => ({ kind: 'topic', value: item.value })),
      ...suggestions.sources.map((item) => ({ kind: 'source', value: item.value })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'cluster',
        eventType: 'impression',
        suggestionKind: item.kind,
        value: item.value,
      }))
    );
  }, [suggestions]);

  if (suggestions.topics.length === 0 && suggestions.sources.length === 0) {
    return null;
  }

  return (
    <section className="cluster-follow-suggestions">
      <div className="cluster-follow-suggestions-head">
        <p className="nyt-section-label flex items-center gap-1 text-muted-foreground">
          <Sparkles size={12} /> {isMK ? 'Следете понатаму' : 'Pratite dalje'}
        </p>
        <p className="cluster-follow-suggestions-copy">
          {isMK 
            ? 'Зачувајте ја темата или изворот што најмногу ја продолжува оваа приказна.' 
            : 'Sačuvajte temu ili izvor koji najbolje nastavlja ovu priču.'}
        </p>
      </div>

      <div className="cluster-follow-suggestions-grid">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.value}`} className="cluster-follow-suggestion-card">
            <div>
              <p className="cluster-follow-suggestion-kicker">{isMK ? 'Предлог тема' : 'Predlog tema'}</p>
              <h4>{item.value}</h4>
              <p className="cluster-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              label={isMK ? `тема: ${item.value}` : `tema: ${item.value}`}
              analyticsSurface="cluster"
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.value}`} className="cluster-follow-suggestion-card">
            <div>
              <p className="cluster-follow-suggestion-kicker">{isMK ? 'Предлог извор' : 'Predlog izvor'}</p>
              <h4>{item.value}</h4>
              <p className="cluster-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              label={isMK ? `извор: ${item.value}` : `izvor: ${item.value}`}
              analyticsSurface="cluster"
            />
          </div>
        ))}
      </div>
    </section>
  );
}
