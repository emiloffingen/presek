import React, { useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile } from '../lib/store.ts';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { useClientTranslations } from '../i18n/clientTranslations';
import { common } from '../i18n/namespaces/common';

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
  lang = 'sr'
}: {
  currentTopic?: string;
  relatedTopics?: TopicSuggestion[];
  strongSources?: SourceSuggestion[];
  lang?: string;
}) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, common);
  const profile = useStore($profile);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const activeProfile = isMounted ? profile : null;

  const suggestions = useMemo(() => {
    const followedTopics = new Set(activeProfile?.followedTopics || []);
    const followedSources = new Set(activeProfile?.followedSources || []);
    const base = buildSurfaceFollowSuggestions(activeProfile, 'topic', { topicLimit: 2, sourceLimit: 1, lang });

    const topicItems = [
      {
        topic: String(currentTopic || '').trim(),
        reason: t('for_you.reason_reading_topic'),
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
  }, [profile, currentTopic, relatedTopics, strongSources, lang]);

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
          <Sparkles size={12} /> {t('for_you.follow_more')}
        </p>
        <p className="topic-follow-suggestions-copy">
          {t('for_you.follow_save_note')}
        </p>
      </div>

      <div className="topic-follow-suggestion-list">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.topic}`} className="topic-follow-suggestion-card">
            <div>
              <p className="topic-follow-suggestion-kicker">{t('for_you.suggest_topic')}</p>
              <h4>{item.topic}</h4>
              <p className="topic-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.topic}
              label={t('for_you.label_topic', { value: item.topic })}
              lang={lang}
              analyticsSurface="topic"
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.source}`} className="topic-follow-suggestion-card">
            <div>
              <p className="topic-follow-suggestion-kicker">{t('for_you.suggest_source')}</p>
              <h4>{item.source}</h4>
              <p className="topic-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.source}
              label={t('for_you.label_source', { value: item.source })}
              lang={lang}
              analyticsSurface="topic"
            />
          </div>
        ))}
      </div>
    </section>
  );
}
