/** Drop headline-scrape noise from trending-entity nav chips. */
const NAV_ENTITY_BLOCKLIST = new Set([
  'evo',
  'ovo',
  'ovoj',
  'ove',
  'ova',
  'srbija',
  'srbije',
  'srbiji',
  'srbiju',
  'srbijom',
  'beograd',
  'beograda',
  'beogradu',
  'vesti',
  'izvor',
  'izvori',
  'danas',
  'juce',
  'juče',
  'sada',
  'novo',
  'nova',
  'najnovije',
]);

export function isNavWorthyEntity(label: string): boolean {
  const clean = label.replace(/^#/, '').trim();
  if (!clean || clean.length < 3) return false;

  const lowered = clean.toLowerCase();
  if (NAV_ENTITY_BLOCKLIST.has(lowered)) return false;

  // Single-token lowercase scraps from titles (e.g. truncated verbs).
  if (!/\s/.test(clean) && clean === clean.toLowerCase() && clean.length < 6) {
    return false;
  }

  return true;
}

export function filterTrendingNavItems<T extends { label?: string; type?: string }>(items: T[]): T[] {
  return items.filter((item) => {
    if (item.type !== 'trending_tag') return true;
    return isNavWorthyEntity(item.label || '');
  });
}
