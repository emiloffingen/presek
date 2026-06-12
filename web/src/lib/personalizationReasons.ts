export function extractReasonItems(reasons: string[] = []): string[] {
  const items: string[] = [];
  for (const reason of reasons) {
    const trimmed = String(reason || '').trim();
    if (!trimmed) continue;
    if (trimmed.includes(':')) {
      items.push(trimmed.split(':').slice(1).join(':').trim());
      continue;
    }
    items.push(trimmed);
  }
  return items.slice(0, 3);
}

export function buildWhyFollowSummary(
  input: {
    whySummary?: string | null;
    matchReasons?: string[] | null;
    matchedTopics?: string[] | null;
    matchedSources?: string[] | null;
  },
  lang: 'sr' | 'mk',
): string {
  if (input.whySummary) return input.whySummary;

  const explicit = [
    ...(input.matchedTopics || []),
    ...(input.matchedSources || []),
  ].filter(Boolean);
  const items = explicit.length > 0 ? explicit.slice(0, 3) : extractReasonItems(input.matchReasons || []);
  if (items.length === 0) return '';

  const prefix = lang === 'mk' ? 'Затоа што следите' : 'Zato što pratite';
  return `${prefix}: ${items.join(', ')}`;
}
