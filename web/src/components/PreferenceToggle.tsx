import React, { useEffect, useState } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import { isFollowingValue, toggleFollowedValue } from '../lib/personalization.js';

export default function PreferenceToggle({
  kind,
  value,
  label,
}: {
  kind: 'topic' | 'source';
  value: string;
  label?: string;
}) {
  const [isFollowing, setIsFollowing] = useState(false);

  useEffect(() => {
    setIsFollowing(isFollowingValue(kind, value));
  }, [kind, value]);

  const onToggle = () => {
    const result = toggleFollowedValue(kind, value);
    setIsFollowing(result.isFollowing);
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

