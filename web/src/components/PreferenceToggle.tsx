import React, { useRef, useState, useMemo, useEffect } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, updateProfile } from '../lib/store.ts';
import {
  recordSuggestionFollow,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';

export default function PreferenceToggle({
  kind,
  value,
  label,
  lang = 'sr',
  onChanged,
  analyticsSurface,
}: {
  kind: 'topic' | 'source';
  value: string;
  label?: string;
  lang?: string;
  onChanged?: (isFollowing: boolean) => void;
  analyticsSurface?: string;
}) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, settings);
  const profile = useStore($profile);
  const field = kind === 'source' ? 'followedSources' : 'followedTopics';
  const isFollowing = useMemo(() => (profile[field] || []).includes(value), [profile, field, value]);

  const [feedback, setFeedback] = useState('');
  const feedbackTimerRef = useRef<number | null>(null);

  const onToggle = () => {
    const nextFollowing = !isFollowing;
    const currentList = profile[field] || [];
    const newList = nextFollowing
        ? [...new Set([...currentList, value])].slice(0, 12)
        : currentList.filter(v => v !== value);

    updateProfile({ [field]: newList });

    if (nextFollowing && analyticsSurface) {
      recordSuggestionFollow(analyticsSurface, kind, value);
      sendSuggestionEvents([{ surface: analyticsSurface, eventType: 'follow', suggestionKind: kind, value }]);
    }

    if (typeof window !== 'undefined' && feedbackTimerRef.current) {
      window.clearTimeout(feedbackTimerRef.current);
    }

    setFeedback(nextFollowing ? t('settings.pref_saved') : t('settings.pref_removed'));
    if (typeof window !== 'undefined') {
      feedbackTimerRef.current = window.setTimeout(() => setFeedback(''), 1800);
    }
    onChanged?.(nextFollowing);
  };

  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && feedbackTimerRef.current) {
        window.clearTimeout(feedbackTimerRef.current);
      }
    };
  }, []);

  const statusId = `pref-status-${kind}-${String(value || '').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'value'}`;

  const displayValue = label || value;
  const shortAction = isFollowing
    ? t('settings.pref_following')
    : kind === 'topic'
      ? t('settings.pref_follow_topic')
      : t('settings.pref_follow_source');
  const clitic = kind === 'topic' ? t('settings.pref_clitic_topic') : t('settings.pref_clitic_source');
  const followVerb = t('settings.pref_follow_verb');
  const negativePrefix = t('settings.pref_not_prefix');
  const buttonLabel = feedback || shortAction;
  const liveMessage = feedback
    ? `${feedback}: ${displayValue}`
    : `${isFollowing ? `${clitic} ${followVerb}` : `${negativePrefix} ${clitic.toLowerCase()} ${followVerb}`} ${displayValue}`;

  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className={`reader-pref-toggle ${isFollowing ? 'is-active' : ''} ${feedback ? 'has-feedback' : ''}`}
        aria-pressed={isFollowing}
        aria-describedby={statusId}
      >
        {isFollowing ? <BellRing size={14} /> : <BellPlus size={14} />}
        <span>{buttonLabel}</span>
      </button>
      <span id={statusId} className="sr-only" aria-live="polite">
        {liveMessage}
      </span>
    </>
  );
}
