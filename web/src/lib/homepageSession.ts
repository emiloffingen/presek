const HOMEPAGE_VISIT_KEY = 'homepage-visit-count';
const HOMEPAGE_EXPANDED_KEY = 'homepage-analysis-expanded';

export function getHomepageVisitCount(): number {
  if (typeof localStorage === 'undefined') return 0;
  return Number(localStorage.getItem(HOMEPAGE_VISIT_KEY) || '0');
}

export function isFirstHomepageSession(): boolean {
  return getHomepageVisitCount() < 1;
}

export function recordHomepageVisit(): number {
  if (typeof localStorage === 'undefined') return 0;
  const next = getHomepageVisitCount() + 1;
  localStorage.setItem(HOMEPAGE_VISIT_KEY, String(next));
  return next;
}

export function hasExpandedHomepageAnalysis(): boolean {
  if (typeof localStorage === 'undefined') return false;
  return localStorage.getItem(HOMEPAGE_EXPANDED_KEY) === '1';
}

export function markHomepageAnalysisExpanded(): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(HOMEPAGE_EXPANDED_KEY, '1');
}
