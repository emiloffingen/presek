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

type TopicSuggestion = {
  topic: string;
  reason: string;
};

type SourceSuggestion = {
  source: string;
  reason: string;
};

export default function TopicFollowSuggestionsIsland({
  currentTopic = '',
  relatedTopics = [],
  strongSources = [],
}: {
  currentTopic?: string;
  relatedTopics?: TopicSuggestion[];
  strongSources?: SourceSuggestion[];
}) {
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    return subscribeToReaderProfile(setProfile);
  }, []);

  const suggestions = useMemo(() => {
    const followedTopics = new Set(profile?.followedTopics || []);
    const followedSources = new Set(profile?.followedSources || []);
    const base = buildSurfaceFollowSuggestions(profile, 'topic', { topicLimit: 2, sourceLimit: 1 });

    const topicItems = [
      {
        topic: String(currentTopic || '').trim(),
        reason: 'Ова е темата што веќе ја читате во длабочина.',
      },
      ...relatedTopics,
      ...base.topics.map((item) => ({ topic: item.value, reason: item.reason })),
    ]
      .filter((item) => item.topic && !followedTopics.has(item.topic))
      .filter((item, index, list) => list.findIndex((entry) => entry.topic === item.topic) === index)
      .slice(0, 3);

    const sourceItems = [...(strongSources || []), ...base.sources.map((item) => ({ source: item.value, reason: item.reason }))]
      .filter((item) => item.source && !followedSources.has(item.source))
      .filter((item, index, list) => list.findIndex((entry) => entry.source === item.source) === index)
      .slice(0, 2);

    return {
      topics: topicItems,
      sources: sourceItems,
    };
  }, [profile, currentTopic, relatedTopics, strongSources]);

  useEffect(() => {
    const result = recordSuggestionImpressions('topic', [
      ...suggestions.topics.map((item) => ({ kind: 'topic', value: item.topic })),
      ...suggestions.sources.map((item) => ({ kind: 'source', value: item.source })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'topic',
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
    <section className="topic-follow-suggestions">
      <div className="topic-follow-suggestions-head">
        <p className="nyt-section-label flex items-center gap-1 text-muted-foreground">
          <Sparkles size={12} /> Следете ја оваа тема подобро
        </p>
        <p className="topic-follow-suggestions-copy">
          Зачувајте ја темата или изворите што најчесто ја водат, за следната достава и „За Вас“ да станат попрецизни.
        </p>
      </div>

      <div className="topic-follow-suggestion-list">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.topic}`} className="topic-follow-suggestion-card">
            <div>
              <p className="topic-follow-suggestion-kicker">Предлог тема</p>
              <h4>{item.topic}</h4>
              <p className="topic-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.topic}
              label={`тема: ${item.topic}`}
              analyticsSurface="topic"
              onChanged={(isFollowing) => {
                if (!isFollowing) setProfile(loadReaderProfile());
              }}
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.source}`} className="topic-follow-suggestion-card">
            <div>
              <p className="topic-follow-suggestion-kicker">Предлог извор</p>
              <h4>{item.source}</h4>
              <p className="topic-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.source}
              label={`извор: ${item.source}`}
              analyticsSurface="topic"
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
