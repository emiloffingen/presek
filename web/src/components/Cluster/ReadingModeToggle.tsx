import React, { useEffect, useState } from 'react';
import { BookOpen, Columns2, LayoutTemplate } from 'lucide-react';
import { applyReadingMode, loadReadingMode, saveReadingMode, type ReadingMode } from '../../lib/readingMode';
import { useTranslations } from '../../i18n/utils';

const MODES: { id: ReadingMode; icon: typeof BookOpen; labelKey: 'reading.standard' | 'reading.focus' | 'reading.compare' }[] = [
  { id: 'standard', icon: LayoutTemplate, labelKey: 'reading.standard' },
  { id: 'focus', icon: BookOpen, labelKey: 'reading.focus' },
  { id: 'compare', icon: Columns2, labelKey: 'reading.compare' },
];

export default function ReadingModeToggle({ lang = 'sr' }: { lang?: string }) {
  const t = useTranslations(lang as 'sr' | 'mk');
  const [mode, setMode] = useState<ReadingMode>('standard');
  const labels = {
    standard: t('reading.standard'),
    focus: t('reading.focus'),
    compare: t('reading.compare'),
  } as const;

  useEffect(() => {
    const initial = loadReadingMode();
    setMode(initial);
    applyReadingMode(initial);
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
