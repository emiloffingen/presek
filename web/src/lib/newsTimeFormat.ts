type NewsTimeLabels = {
  just_now: string;
  ago: string;
  min_short: string;
  hour: string;
  hours: string;
  day: string;
  days: string;
};

export function getRelativeTimeStr(dateStr: string, lang: 'sr' | 'mk', labels: NewsTimeLabels): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 1) return labels.just_now;
    if (diffMins < 60) return `${labels.ago} ${diffMins} ${labels.min_short}`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) {
      const label = diffHours === 1 ? labels.hour : labels.hours;
      return `${labels.ago} ${diffHours} ${label}`;
    }

    const diffDays = Math.floor(diffHours / 24);
    const label = diffDays === 1 ? labels.day : labels.days;
    return `${labels.ago} ${diffDays} ${label}`;
  } catch {
    return '';
  }
}

export function getClockTimeStr(dateStr: string, lang: 'sr' | 'mk', labels: NewsTimeLabels): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 1) return labels.just_now;
    if (diffMins < 60) return `${labels.ago} ${diffMins} ${labels.min_short}`;

    return date.toLocaleTimeString(lang === 'sr' ? 'sr-RS' : 'mk-MK', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Europe/Belgrade',
    });
  } catch {
    return '';
  }
}
