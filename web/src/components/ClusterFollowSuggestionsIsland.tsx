import React, { useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  loadReaderProfile,
  recordSuggestionImpressions,
  sendSuggestionEvents,
  subscribeToReaderProfile,
} from '../lib/personalization.js';

type Suggestion = {
  value: string;
  reason: string;
};

export default function ClusterFollowSuggestionsIsland({
  topic = '',
  source = '',
  adjacentTopic = '',
}: {
  topic?: string;
  source?: string;
  adjacentTopic?: string;
}) {
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    return subscribeToReaderProfile(setProfile);
  }, []);

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
      reason: 'Ова е главната тема на кластерот што го читате.',
    }, followedTopics);
    addUnique(topicSuggestions, {
      value: String(adjacentTopic || '').trim(),
      reason: 'Оваа поврзана тема често ја носи следната развојна линија.',
    }, followedTopics);
    addUnique(sourceSuggestions, {
      value: String(source || '').trim(),
      reason: 'Овој извор ја води главната линија во кластерот што го читате.',
    }, followedSources);

    return {
      topics: topicSuggestions.slice(0, 2),
      sources: sourceSuggestions.slice(0, 2),
    };
  }, [profile, topic, source, adjacentTopic]);

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
          <Sparkles size={12} /> Следете ја темата
        </p>
        <p className="cluster-follow-suggestions-copy">
          Брзо зачувајте ја темата или изворот што најмногу го отвора овој кластер.
        </p>
      </div>

      <div className="cluster-follow-suggestions-grid">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.value}`} className="cluster-follow-suggestion-card">
            <div>
              <p className="cluster-follow-suggestion-kicker">Предлог тема</p>
              <h4>{item.value}</h4>
              <p className="cluster-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              label={`тема: ${item.value}`}
              analyticsSurface="cluster"
              onChanged={(isFollowing) => {
                if (!isFollowing) setProfile(loadReaderProfile());
              }}
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.value}`} className="cluster-follow-suggestion-card">
            <div>
              <p className="cluster-follow-suggestion-kicker">Предлог извор</p>
              <h4>{item.value}</h4>
              <p className="cluster-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              label={`извор: ${item.value}`}
              analyticsSurface="cluster"
              onChanged={(isFollowing) => {
                if (!isFollowing) setProfile(loadReaderProfile());
              }}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
