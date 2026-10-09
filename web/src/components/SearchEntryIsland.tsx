import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { search } from '../i18n/namespaces/search';
import { common } from '../i18n/namespaces/common';
import type { Locale } from '../lib/localePaths';

// The overlay (results, preview, voice search, filters) is only needed once the
// user opens search, so keep it out of the chunk every page loads.
const loadSearchIsland = () => import('./SearchIsland');
const SearchIsland = lazy(loadSearchIsland);

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

function prefetchSearch() {
  void loadSearchIsland();
}

function SearchTriggerButton({ onClick, lang }: { onClick: () => void; lang: Locale }) {
  const t = useClientTranslations(lang, search, common);

  return (
    <button
      type="button"
      onClick={onClick}
      onPointerEnter={prefetchSearch}
      onFocus={prefetchSearch}
      data-testid="search-trigger"
      className="presek-search-trigger group"
      aria-label={t('search.open_search')}
      aria-keyshortcuts="Meta+K /"
    >
      <span className="search-trigger-icon" aria-hidden="true">
        <Search size={16} strokeWidth={2.25} />
      </span>
      <span className="search-trigger-copy">
        <span className="search-trigger-label">{t('header.search_placeholder')}</span>
        <span className="search-trigger-hint">{t('search.hint_topics')}</span>
      </span>
      <span className="search-trigger-shortcuts" aria-hidden="true">
        <kbd className="search-trigger-kbd search-trigger-kbd--slash">/</kbd>
        <kbd className="search-trigger-kbd search-trigger-kbd--meta">
          <span className="search-trigger-kbd-meta">⌘</span>K
        </kbd>
      </span>
    </button>
  );
}

import { ErrorBoundary } from './ui/ErrorBoundary';

function SearchEntryIslandContent({
  initialQuery = '',
  lang = 'mk',
}: {
  initialQuery?: string | null;
  lang?: Locale;
}) {
  const eager = Boolean(initialQuery && String(initialQuery).trim());
  const [active, setActive] = useState(eager);
  const open = useCallback(() => setActive(true), []);
  const close = useCallback(() => setActive(false), []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    if ((window as any).__presek_search_open_requested) {
      open();
      (window as any).__presek_search_open_requested = false;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        open();
        return;
      }
      if (e.key === '/' && !isEditableTarget(e.target)) {
        e.preventDefault();
        open();
      }
    };

    const handleOpenEvent = () => open();

    const handleFabClick = (e: MouseEvent) => {
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (target.closest('[data-presek-search-fab]')) {
        e.preventDefault();
        open();
      }
    };

    // Warm the overlay chunk once the page is idle so the first open is instant.
    const idle = (window as any).requestIdleCallback as undefined | ((cb: () => void, o?: { timeout: number }) => number);
    const idleHandle = idle ? idle(prefetchSearch, { timeout: 4000 }) : window.setTimeout(prefetchSearch, 2500);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('presek:open-search', handleOpenEvent);
    document.addEventListener('click', handleFabClick);
    return () => {
      const cancelIdle = (window as any).cancelIdleCallback as undefined | ((h: number) => void);
      if (idle && cancelIdle) cancelIdle(idleHandle);
      else window.clearTimeout(idleHandle);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('presek:open-search', handleOpenEvent);
      document.removeEventListener('click', handleFabClick);
    };
  }, [open]);

  if (!active) {
    return <SearchTriggerButton onClick={open} lang={lang} />;
  }

  return (
    <Suspense fallback={<SearchTriggerButton onClick={open} lang={lang} />}>
      <SearchIsland
        initialQuery={initialQuery}
        lang={lang}
        startOpen
        hideTrigger
        onClose={close}
      />
    </Suspense>
  );
}

export default function SearchEntryIsland({
  initialQuery = '',
  lang = 'mk',
}: {
  initialQuery?: string | null;
  lang?: Locale;
}) {
  return (
    <ErrorBoundary lang={lang}>
      <SearchEntryIslandContent initialQuery={initialQuery} lang={lang} />
    </ErrorBoundary>
  );
}
