export type ReadingMode = 'standard' | 'focus' | 'compare';

const STORAGE_KEY = 'reading-mode';
const LEGACY_READER_KEY = 'readerMode';

export function loadReadingMode(): ReadingMode {
  if (typeof localStorage === 'undefined') return 'standard';
  let stored = null;
  let legacyStored = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
    legacyStored = localStorage.getItem(LEGACY_READER_KEY);
  } catch (e) {
    console.warn('localStorage not accessible:', e);
  }
  if (stored === 'standard' || stored === 'focus' || stored === 'compare') return stored;
  if (stored === 'zen') return 'focus';
  if (!stored && legacyStored === 'true') return 'focus';
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.get('reader') === '1') return 'focus';
  }
  return 'standard';
}

export function saveReadingMode(mode: ReadingMode): ReadingMode {
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
      localStorage.setItem(LEGACY_READER_KEY, mode === 'focus' ? 'true' : 'false');
    } catch (e) {}
  }
  return mode;
}

function syncClusterReadingDom(mode: ReadingMode) {
  const article = document.querySelector('.cluster-article-container');
  const sidebar = document.querySelector('.editorial-sidebar-col');
  document.body.classList.remove('zen-mode', 'compare-mode', 'reader-mode-active');
  article?.classList.remove('reader-focused');
  sidebar?.classList.remove('is-expanded');
  const sidebarDetails = document.querySelector('.cluster-sidebar-details');
  if (sidebarDetails instanceof HTMLDetailsElement) {
    sidebarDetails.open = false;
  }

  if (mode === 'focus') {
    document.body.classList.add('zen-mode', 'reader-mode-active');
    article?.classList.add('reader-focused');
  } else if (mode === 'compare') {
    document.body.classList.add('compare-mode');
    window.dispatchEvent(
      new CustomEvent('presek:sidebar-tab', { detail: { tab: 'compare' } }),
    );
  }
}

export function applyReadingMode(mode: ReadingMode) {
  if (typeof document === 'undefined') return;
  syncClusterReadingDom(mode);
  window.dispatchEvent(
    new CustomEvent('presek:reading-mode-changed', { detail: { mode } }),
  );
}
