import React, { useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildSurfaceFollowSuggestions,
  hasPersonalizationSignal,
  loadReaderProfile,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';

export default function HomeRailSuggestionsIsland() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    setProfile(loadReaderProfile());
  }, [refreshKey]);

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
          <Sparkles size={14} /> СЛЕДЕТЕ ПОАМЕТНО
        </h3>
        <p className="rail-note">
          Неколку брзи следења се доволни `За Вас`, известувањата и неделниот преглед да станат многу попрецизни.
        </p>
      </div>

      <div className="rail-suggestion-list">
        {suggestions.topics.map((item) => (
          <div key={`topic:${item.value}`} className="rail-suggestion-card">
            <div>
              <p className="rail-suggestion-kicker">Тема</p>
              <strong>{item.value}</strong>
              <p>{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="topic"
              value={item.value}
              label={`тема: ${item.value}`}
              analyticsSurface="home_rail"
              onChanged={() => setRefreshKey((value) => value + 1)}
            />
          </div>
        ))}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.value}`} className="rail-suggestion-card">
            <div>
              <p className="rail-suggestion-kicker">Извор</p>
              <strong>{item.value}</strong>
              <p>{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              label={`извор: ${item.value}`}
              analyticsSurface="home_rail"
              onChanged={() => setRefreshKey((value) => value + 1)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
