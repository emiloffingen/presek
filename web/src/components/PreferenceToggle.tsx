import React, { useEffect, useState } from 'react';
import { BellPlus, BellRing } from 'lucide-react';
import { isFollowingValue, toggleFollowedValue } from '../lib/personalization.js';

export default function PreferenceToggle({
  kind,
  value,
  label,
  onChanged,
}: {
  kind: 'topic' | 'source';
  value: string;
  label?: string;
  onChanged?: (isFollowing: boolean) => void;
}) {
  const [isFollowing, setIsFollowing] = useState(false);

  useEffect(() => {
    setIsFollowing(isFollowingValue(kind, value));
  }, [kind, value]);

  const onToggle = () => {
    const result = toggleFollowedValue(kind, value);
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
