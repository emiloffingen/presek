import React, { useEffect, useMemo } from 'react';
import { Sparkles } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile } from '../lib/store.ts';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  hasPersonalizationSignal,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';

export default function HomeRailSuggestionsIsland() {
  const profile = useStore($profile);

  const suggestions = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'home_rail', { topicLimit: 2, sourceLimit: 1 }),
    [profile]
  );
  const followedCount = (profile?.followedTopics || []).length + (profile?.followedSources || []).length;
  const show = suggestions.topics.length + suggestions.sources.length > 0 && (!hasPersonalizationSignal(profile) || followedCount < 4);

  useEffect(() => {
    if (!show) return;
    const result = recordSuggestionImpressions('home_rail', [
      ...suggestions.topics.map((item) => ({ kind: 'topic', value: item.value })),
      ...suggestions.sources.map((item) => ({ kind: 'source', value: item.value })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'home_rail',
        eventType: 'impression',
        suggestionKind: item.kind,
        value: item.value,
      }))
    );
  }, [show, suggestions]);

  if (!show) {
    return null;
  }

  return (
    <section className="rail-module rail-suggestions">
      <div className="rail-suggestions-head">
        <h3 className="rail-title">
          <Sparkles size={14} /> STO DA SLEDITE
        </h3>
        <p className="rail-note">
          Nekolku sledenja se dovolni za `Za Vas` i dostavata da stanat poprecizni.
        </p>
      </div>

      <div className="rail-suggestion-list">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.value}`} className="rail-suggestion-card">
            <div>
              <p className="rail-suggestion-kicker">Tema</p>
              <strong>{item.value}</strong>
              <p>{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              label={`tema: ${item.value}`}
              analyticsSurface="home_rail"
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.value}`} className="rail-suggestion-card">
            <div>
              <p className="rail-suggestion-kicker">izvor</p>
              <strong>{item.value}</strong>
              <p>{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              label={`izvor: ${item.value}`}
              analyticsSurface="home_rail"
            />
          </div>
        ))}
      </div>
    </section>
  );
}
