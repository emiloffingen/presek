export type SiteLang = 'sr' | 'mk';

export type ClusterSignalInput = {
  pluralismScore?: number | null;
  pulseScore?: number | null;
  isBreaking?: boolean;
  topic?: string;
};

export type SignalBadge = {
  key: string;
  labelKey: string;
  tone?: 'conflict' | 'consensus' | 'hot' | 'topic';
};

const PLURALISM_CONFLICT = 55;
const PLURALISM_CONSENSUS = 15;
const PULSE_HOT = 80;

export function getVisibleCardSignals(input: ClusterSignalInput, maxBadges = 1): SignalBadge[] {
  const badges: SignalBadge[] = [];

  if (input.isBreaking) {
    badges.push({ key: 'breaking', labelKey: 'signal.breaking', tone: 'hot' });
  }

  const pluralism = input.pluralismScore;
  if (pluralism != null && pluralism >= PLURALISM_CONFLICT) {
    badges.push({ key: 'pluralism-conflict', labelKey: 'signal.different_angles', tone: 'conflict' });
  } else if (pluralism != null && pluralism <= PLURALISM_CONSENSUS) {
    badges.push({ key: 'pluralism-consensus', labelKey: 'signal.same_story', tone: 'consensus' });
  }

  const pulse = input.pulseScore;
  if (pulse != null && pulse >= PULSE_HOT) {
    badges.push({ key: 'pulse-hot', labelKey: 'signal.trending', tone: 'hot' });
  }

  if (badges.length === 0 && input.topic) {
    badges.push({ key: 'topic', labelKey: 'signal.topic', tone: 'topic' });
  }

  return badges.slice(0, maxBadges);
}

export function formatSignalBadge(
  badge: SignalBadge,
  lang: SiteLang,
  values: { pluralism?: number; pulse?: number; topic?: string },
  t: (key: string, params?: Record<string, string | number>) => string, // eslint-disable-line @typescript-eslint/no-explicit-any
): string {
  if (badge.key === 'pluralism-conflict' && values.pluralism != null) {
    return `${t(badge.labelKey)} ${values.pluralism}%`;
  }
  if (badge.key === 'pulse-hot' && values.pulse != null) {
    return `${t(badge.labelKey)} ${values.pulse}%`;
  }
  if (badge.key === 'topic' && values.topic) {
    return values.topic;
  }
  return t(badge.labelKey);
}
