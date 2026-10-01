import React, { useEffect, useState } from 'react';
import { BookOpen, Columns2, LayoutTemplate } from 'lucide-react';
import { applyReadingMode, loadReadingMode, saveReadingMode, type ReadingMode } from '../../lib/readingMode';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { settings } from '../../i18n/namespaces/settings';

const MODES: { id: ReadingMode; icon: typeof BookOpen; labelKey: 'reading.standard' | 'reading.focus' | 'reading.compare' }[] = [
  { id: 'standard', icon: LayoutTemplate, labelKey: 'reading.standard' },
  { id: 'focus', icon: BookOpen, labelKey: 'reading.focus' },
  { id: 'compare', icon: Columns2, labelKey: 'reading.compare' },
];

export default function ReadingModeToggle({ lang = 'mk' }: { lang?: string }) {
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);
  const [mode, setMode] = useState<ReadingMode>('standard');
  const labels = {
    standard: t('reading.standard'),
    focus: t('reading.focus'),
    compare: t('reading.compare'),
  } as const;

  useEffect(() => {
    const body = document.body;
    // Respect a mode another island already applied (e.g. the mobile auto-focus
    // banner) instead of resetting it to standard on mount.
    const domMode: ReadingMode | null = body.classList.contains('compare-mode')
      ? 'compare'
      : body.classList.contains('zen-mode')
        ? 'focus'
        : null;
    const initial = domMode || loadReadingMode();
    setMode(initial);
    if (!domMode) applyReadingMode(initial);
  }, []);

  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ mode?: typeof mode }>).detail;
      if (detail?.mode) setMode(detail.mode);
    };
    window.addEventListener('presek:reading-mode-changed', onChange);
    return () => window.removeEventListener('presek:reading-mode-changed', onChange);
  }, []);

  const selectMode = (next: ReadingMode) => {
    setMode(next);
    saveReadingMode(next);
    applyReadingMode(next);
  };

  return (
    <div className="reading-mode-toggle" role="group" aria-label={t('reading.label')}>
      {MODES.map(({ id, icon: Icon }) => (
        <button
          key={id}
          type="button"
          className={`reading-mode-btn ${mode === id ? 'is-active' : ''}`}
          aria-pressed={mode === id}
          aria-label={labels[id]}
          title={labels[id]}
          onClick={() => selectMode(id)}
        >
          <Icon size={14} strokeWidth={2.25} />
          <span>{labels[id]}</span>
        </button>
      ))}
    </div>
  );
}
