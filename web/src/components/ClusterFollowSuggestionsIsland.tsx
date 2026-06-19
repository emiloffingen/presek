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

type Suggestion = {
  value: string;
  reason: string;
};

const TOPIC_LABELS: Record<string, { sr: string; mk: string }> = {
  ekonomija: { sr: 'Ekonomija', mk: 'Економија' },
  kultura: { sr: 'Kultura', mk: 'Култура' },
  makedonija: { sr: 'Makedonija', mk: 'Македонија' },
  politika: { sr: 'Politika', mk: 'Политика' },
  region: { sr: 'Region', mk: 'Регион' },
  srbija: { sr: 'Srbija', mk: 'Србија' },
  sport: { sr: 'Sport', mk: 'Спорт' },
  svet: { sr: 'Svet', mk: 'Свет' },
  tehnologija: { sr: 'Tehnologija', mk: 'Технологија' },
  vesti: { sr: 'Vesti', mk: 'Вести' },
  zabava: { sr: 'Zabava', mk: 'Забава' },
  zdravje: { sr: 'Zdravlje', mk: 'Здравје' },
  zivot: { sr: 'Život', mk: 'Живот' },
  život: { sr: 'Život', mk: 'Живот' },
};

function displayTopicLabel(value: string, lang: string) {
  const clean = String(value || '').trim();
  if (!clean) return '';
  const mapped = TOPIC_LABELS[clean.toLowerCase()];
  return mapped ? (lang === 'mk' ? mapped.mk : mapped.sr) : clean;
}

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
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, common);
  const profile = useStore($profile);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const activeProfile = isMounted ? profile : null;

  const suggestions = useMemo(() => {
    const base = buildSurfaceFollowSuggestions(activeProfile, 'cluster', { topicLimit: 2, sourceLimit: 1, lang });
    const followedTopics = new Set(activeProfile?.followedTopics || []);
    const followedSources = new Set(activeProfile?.followedSources || []);

    const topicSuggestions: Suggestion[] = [...base.topics];
    const sourceSuggestions: Suggestion[] = [...base.sources];

    const addUnique = (list: Suggestion[], item: Suggestion, existing: Set<string>) => {
      if (!item.value || existing.has(item.value) || list.some((entry) => entry.value === item.value)) return;
      list.unshift(item);
    };

    addUnique(topicSuggestions, {
      value: String(topic || '').trim(),
      reason: t('for_you.reason_cluster_main_topic'),
    }, followedTopics);

    if (adjacentTopic) {
        addUnique(topicSuggestions, {
          value: String(adjacentTopic || '').trim(),
          reason: t('for_you.reason_adjacent_topic'),
        }, followedTopics);
    }

    addUnique(sourceSuggestions, {
      value: String(source || '').trim(),
      reason: t('for_you.reason_cluster_main_source'),
    }, followedSources);

    return {
      topics: topicSuggestions.slice(0, 2),
      sources: sourceSuggestions.slice(0, 2),
    };
  }, [profile, topic, source, adjacentTopic, lang]);

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
          <Sparkles size={12} /> {t('for_you.follow_more')}
        </p>
        <p className="cluster-follow-suggestions-copy">
          {t('for_you.follow_cluster_note')}
        </p>
      </div>

      <div className="cluster-follow-suggestions-grid">
        {suggestions.topics.map((item) => {
          const displayValue = displayTopicLabel(item.value, lang);
          return (
            <div key={`topic:${item.value}`} className="cluster-follow-suggestion-card">
              <div>
                <p className="cluster-follow-suggestion-kicker">{t('for_you.suggest_topic')}</p>
                <h4>{displayValue}</h4>
                <p className="cluster-follow-suggestion-reason">{item.reason}</p>
              </div>
              <PreferenceToggle
                kind="topic"
                value={item.value}
                label={t('for_you.label_topic', { value: displayValue })}
                lang={lang}
                analyticsSurface="cluster"
              />
            </div>
          );
        })}

        {suggestions.sources.map((item) => (
          <div key={`source:${item.value}`} className="cluster-follow-suggestion-card">
            <div>
              <p className="cluster-follow-suggestion-kicker">{t('for_you.suggest_source')}</p>
              <h4>{item.value}</h4>
              <p className="cluster-follow-suggestion-reason">{item.reason}</p>
            </div>
            <PreferenceToggle
              kind="source"
              value={item.value}
              label={t('for_you.label_source', { value: item.value })}
              lang={lang}
              analyticsSurface="cluster"
            />
          </div>
        ))}
      </div>
    </section>
  );
}
