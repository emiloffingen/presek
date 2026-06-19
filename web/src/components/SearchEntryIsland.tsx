import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { search } from '../i18n/namespaces/search';
import { common } from '../i18n/namespaces/common';
import type { Locale } from '../lib/localePaths';

const SearchIsland = lazy(() => import('./SearchIsland'));

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

function SearchTriggerButton({ onClick, lang }: { onClick: () => void; lang: Locale }) {
  const t = useClientTranslations(lang, search, common);

  return (
    <button
      type="button"
      onClick={onClick}
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

export default function SearchEntryIsland({
  initialQuery = '',
  lang = 'sr',
}: {
  initialQuery?: string | null;
  lang?: Locale;
}) {
  const eager = Boolean(initialQuery && String(initialQuery).trim());
  const [active, setActive] = useState(eager);
  const open = useCallback(() => setActive(true), []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

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

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('presek:open-search', handleOpenEvent);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('presek:open-search', handleOpenEvent);
    };
  }, [open]);

  if (!active) {
    return <SearchTriggerButton onClick={open} lang={lang} />;
  }

  return (
    <Suspense fallback={<SearchTriggerButton onClick={open} lang={lang} />}>
      <SearchIsland initialQuery={initialQuery} lang={lang} startOpen />
    </Suspense>
  );
}
