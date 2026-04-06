import React, { useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import { buildFollowRecommendations, loadReaderProfile } from '../lib/personalization.js';

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
  const [refreshKey, setRefreshKey] = useState(0);
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    setProfile(loadReaderProfile());
  }, [refreshKey]);

  const suggestions = useMemo(() => {
    const base = buildFollowRecommendations(profile, 3);
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

  if (suggestions.topics.length === 0 && suggestions.sources.length === 0) {
    return null;
  }

  return (
    <section className="cluster-follow-suggestions">
      <div className="cluster-follow-suggestions-head">
        <p className="nyt-section-label flex items-center gap-1 text-muted-foreground">
          <Sparkles size={12} /> Следете го ова подобро
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
              onChanged={() => setRefreshKey((value) => value + 1)}
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
              onChanged={() => setRefreshKey((value) => value + 1)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
