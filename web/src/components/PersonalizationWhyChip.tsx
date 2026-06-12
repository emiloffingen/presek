import React from 'react';
import { Sparkles } from 'lucide-react';
import { buildWhyFollowSummary } from '../lib/personalizationReasons';

type Props = {
  lang?: 'sr' | 'mk';
  reason?: string | null;
  matchReasons?: string[] | null;
  matchedTopics?: string[] | null;
  matchedSources?: string[] | null;
  whySummary?: string | null;
  variant?: 'compact' | 'detail';
};

export default function PersonalizationWhyChip({
  lang = 'sr',
  reason = null,
  matchReasons = [],
  matchedTopics = [],
  matchedSources = [],
  whySummary = null,
  variant = 'compact',
}: Props) {
  const summary = buildWhyFollowSummary(
    { whySummary, matchReasons, matchedTopics, matchedSources },
    lang,
  );
  const detail = reason || matchReasons?.[0] || summary;
  const label = variant === 'detail' ? detail : summary || detail;

  if (!label) return null;

  return (
    <p className={`personalization-why-chip personalization-why-chip--${variant}`} title={detail || undefined}>
      <Sparkles size={12} aria-hidden="true" />
      <span>{label}</span>
    </p>
  );
}
