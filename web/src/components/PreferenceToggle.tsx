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
  onChanged,
  analyticsSurface,
}: {
  kind: 'topic' | 'source';
  value: string;
  label?: string;
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

    setFeedback(nextFollowing ? 'Зачувано' : 'Отстрането');
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

  const shortAction = isFollowing ? 'Се следи' : kind === 'topic' ? 'Следи тема' : 'Следи извор';
  const clitic = kind === 'topic' ? 'Ја' : 'Го';
  const buttonLabel = feedback || shortAction;
  const liveMessage = feedback
    ? `${feedback}: ${value}`
    : `${isFollowing ? clitic + ' следите' : 'Не ' + clitic.toLowerCase() + ' следите'} ${value}`;

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
