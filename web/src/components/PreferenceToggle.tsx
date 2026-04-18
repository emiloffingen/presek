import React, { useEffect, useRef, useState } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import {
  isFollowingValue,
  recordSuggestionFollow,
  sendSuggestionEvents,
  subscribeToReaderProfile,
  toggleFollowedValue,
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
  const [isFollowing, setIsFollowing] = useState(false);
  const [feedback, setFeedback] = useState('');
  const feedbackTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setIsFollowing(isFollowingValue(kind, value));
  }, [kind, value]);

  useEffect(() => subscribeToReaderProfile(() => {
    setIsFollowing(isFollowingValue(kind, value));
  }), [kind, value]);

  useEffect(() => () => {
    if (feedbackTimerRef.current) {
      window.clearTimeout(feedbackTimerRef.current);
    }
  }, []);

  const onToggle = () => {
    const result = toggleFollowedValue(kind, value);
    if (result.isFollowing && analyticsSurface) {
      const tracked = recordSuggestionFollow(analyticsSurface, kind, value);
      if (tracked.recorded) {
        sendSuggestionEvents([{ surface: analyticsSurface, eventType: 'follow', suggestionKind: kind, value }]);
      }
    }

    if (feedbackTimerRef.current) {
      window.clearTimeout(feedbackTimerRef.current);
    }

    setFeedback(result.isFollowing ? 'Зачувано' : 'Отстрането');
    feedbackTimerRef.current = window.setTimeout(() => setFeedback(''), 1800);
    setIsFollowing(result.isFollowing);
    onChanged?.(result.isFollowing);
  };

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
