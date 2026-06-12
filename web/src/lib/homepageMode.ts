export type HomepageMode = 'vesti' | 'analiza';

const STORAGE_KEY = 'homepage-mode';
const VISIT_COUNT_KEY = 'cluster-visit-count';
const ANALIZA_THRESHOLD = 3;

export function loadHomepageMode(): HomepageMode {
  if (typeof localStorage === 'undefined') return 'vesti';
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'vesti' || stored === 'analiza') return stored;

  const visits = Number(localStorage.getItem(VISIT_COUNT_KEY) || '0');
  return visits >= ANALIZA_THRESHOLD ? 'analiza' : 'vesti';
}

export function saveHomepageMode(mode: HomepageMode): HomepageMode {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, mode);
  }
  return mode;
}

export function recordClusterVisit(): number {
  if (typeof localStorage === 'undefined') return 0;
  const next = Number(localStorage.getItem(VISIT_COUNT_KEY) || '0') + 1;
  localStorage.setItem(VISIT_COUNT_KEY, String(next));
  return next;
}
