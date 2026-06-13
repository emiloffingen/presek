export type StoryFreshnessLang = 'sr' | 'mk';

export type StoryFreshnessInput = {
  lang: StoryFreshnessLang;
  synthesisUpdatedAt?: string | null;
  latestArticleAt?: string | null;
  isStale?: boolean;
  newArticleCount?: number;
  pipelineBusy?: boolean;
  missingSynthesis?: boolean;
};

export type StoryFreshnessView = {
  label: string;
  ariaLabel: string;
  tone: 'fresh' | 'aging' | 'stale' | 'pending';
};

type Translator = (
  key: string,
  params?: Record<string, string | number>,
) => string;

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function relativeTimeLabel(date: Date, t: Translator): string {
  const diffMins = Math.floor((Date.now() - date.getTime()) / (1000 * 60));
  if (diffMins < 1) return t('news.just_now');
  if (diffMins < 60) return `${t('news.ago')} ${diffMins} ${t('news.min_short')}`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) {
    const label = diffHours === 1 ? t('news.hour') : t('news.hours');
    return `${t('news.ago')} ${diffHours} ${label}`;
  }

  const diffDays = Math.floor(diffHours / 24);
  const label = diffDays === 1 ? t('news.day') : t('news.days');
  return `${t('news.ago')} ${diffDays} ${label}`;
}

export function formatStoryFreshness(
  input: StoryFreshnessInput,
  t: Translator,
): StoryFreshnessView | null {
  const missingSynthesis = Boolean(input.missingSynthesis);
  if (missingSynthesis) {
    return {
      label: t('freshness.pending_synthesis'),
      ariaLabel: t('freshness.pending_synthesis'),
      tone: 'pending',
    };
  }

  const latestArticleAt = parseDate(input.latestArticleAt);
  const synthesisUpdatedAt = parseDate(input.synthesisUpdatedAt);
  const anchor = synthesisUpdatedAt || latestArticleAt;
  if (!anchor) return null;

  const diffMins = Math.floor((Date.now() - anchor.getTime()) / (1000 * 60));
  const newCount = Number(input.newArticleCount || 0);
  const pipelineBusy = Boolean(input.pipelineBusy);

  if (input.isStale || pipelineBusy) {
    if (input.isStale && newCount > 0) {
      return {
        label: t('freshness.stale_new_reports', { count: newCount }),
        ariaLabel: t('freshness.stale_new_reports', { count: newCount }),
        tone: 'stale',
      };
    }
    return {
      label: t('freshness.stale_updating'),
      ariaLabel: t('freshness.stale_updating'),
      tone: 'stale',
    };
  }

  const relative = relativeTimeLabel(anchor, t);
  const label = t('freshness.updated', { time: relative });
  const tone = diffMins <= 20 ? 'fresh' : diffMins <= 120 ? 'aging' : 'aging';

  return {
    label,
    ariaLabel: label,
    tone,
  };
}
