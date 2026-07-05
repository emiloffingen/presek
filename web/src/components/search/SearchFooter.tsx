import { Globe, Sparkles } from 'lucide-react';
import type { TFunction } from './types';

type SearchFooterProps = {
  t: TFunction;
};

export function SearchFooter({ t }: SearchFooterProps) {
  return (
    <div className="px-4 sm:px-6 py-2.5 sm:py-3 border-t border-border/40 bg-secondary/5 flex items-center justify-between search-cmd-footer-hint gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] sm:text-[11px]">
        <span className="flex items-center gap-1">
          <kbd className="px-1 py-0.5 bg-background border border-border rounded-none">Enter</kbd>{' '}
          {t('search.shortcut_select')}
        </span>
        <span className="hidden sm:flex items-center gap-1">
          <kbd className="px-1 py-0.5 bg-background border border-border rounded-none">↑</kbd>
          <kbd className="px-1 py-0.5 bg-background border border-border rounded-none">↓</kbd>{' '}
          {t('search.shortcut_nav')}
        </span>
        <span className="flex items-center gap-1">
          <kbd className="px-1 py-0.5 bg-background border border-border rounded-none">Esc</kbd>{' '}
          {t('search.shortcut_close')}
        </span>
      </div>
      <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)]">
        <span className="flex items-center gap-1.5">
          <Globe size={12} /> {t('search.global_search')}
        </span>
        <span className="hidden sm:inline w-1 h-1 rounded-full bg-border" />
        <span className="hidden sm:flex items-center gap-1.5">
          <Sparkles size={12} /> {t('search.smart_assist')}
        </span>
      </div>
    </div>
  );
}
