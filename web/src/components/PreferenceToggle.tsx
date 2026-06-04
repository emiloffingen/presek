import React, { useRef, useState, useMemo, useEffect } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, updateProfile } from '../lib/store.ts';
import {
  recordSuggestionFollow,
  sendSuggestionEvents,
} from '../lib/personalization.js';

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

    setFeedback(nextFollowing
      ? (lang === 'mk' ? 'Зачувано' : 'Sačuvano')
      : (lang === 'mk' ? 'Отстрането' : 'Uklonjeno'));
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

  const isMK = lang === 'mk';
  const displayValue = label || value;
  const shortAction = isFollowing
    ? (isMK ? 'Се следи' : 'Se prati')
    : kind === 'topic'
      ? (isMK ? 'Следи тема' : 'Prati temu')
      : (isMK ? 'Следи извор' : 'Prati izvor');
  const clitic = isMK
    ? (kind === 'topic' ? 'Ја' : 'Го')
    : (kind === 'topic' ? 'Je' : 'Ga');
  const followVerb = isMK ? 'следите' : 'pratite';
  const negativePrefix = isMK ? 'Не' : 'Ne';
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
