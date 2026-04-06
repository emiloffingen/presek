import React, { useEffect, useState } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import { isFollowingValue, recordSuggestionFollow, sendSuggestionEvents, toggleFollowedValue } from '../lib/personalization.js';

export default function PreferenceToggle({
  kind,
  value,
  label,
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

  useEffect(() => {
    setIsFollowing(isFollowingValue(kind, value));
  }, [kind, value]);

  const onToggle = () => {
    const result = toggleFollowedValue(kind, value);
    if (result.isFollowing && analyticsSurface) {
      const tracked = recordSuggestionFollow(analyticsSurface, kind, value);
      if (tracked.recorded) {
        sendSuggestionEvents([{ surface: analyticsSurface, eventType: 'follow', suggestionKind: kind, value }]);
      }
    }
    setIsFollowing(result.isFollowing);
    onChanged?.(result.isFollowing);
  };

  const noun = label || (kind === 'topic' ? 'тема' : 'извор');

  return (
    <button
      type="button"
      onClick={onToggle}
      className={`reader-pref-toggle ${isFollowing ? 'is-active' : ''}`}
      aria-pressed={isFollowing}
    >
      {isFollowing ? <BellRing size={14} /> : <BellPlus size={14} />}
      <span>{isFollowing ? `Следите ${noun}` : `Следи ${noun}`}</span>
    </button>
  );
}
