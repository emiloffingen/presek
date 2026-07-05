const VISIT_COUNT_KEY = 'cluster-visit-count';

export function recordClusterVisit(): number {
  if (typeof localStorage === 'undefined') return 0;
  let next = 1;
  try {
    next = Number(localStorage.getItem(VISIT_COUNT_KEY) || '0') + 1;
    localStorage.setItem(VISIT_COUNT_KEY, String(next));
  } catch (e) {}
  return next;
}
