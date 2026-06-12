export type ReadingMode = 'standard' | 'focus' | 'compare';

const STORAGE_KEY = 'reading-mode';

export function loadReadingMode(): ReadingMode {
  if (typeof localStorage === 'undefined') return 'standard';
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'standard' || stored === 'focus' || stored === 'compare') return stored;
  if (stored === 'zen') return 'focus';
  return 'standard';
}

export function saveReadingMode(mode: ReadingMode): ReadingMode {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, mode);
  }
  return mode;
}

export function applyReadingMode(mode: ReadingMode) {
  if (typeof document === 'undefined') return;
  document.body.classList.remove('zen-mode', 'compare-mode');
  if (mode === 'focus') document.body.classList.add('zen-mode');
  if (mode === 'compare') document.body.classList.add('compare-mode');
}
