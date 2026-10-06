import React, { useState, useEffect, useRef } from 'react';
import { Type, Check } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';

const SCALES = [
  { value: '1', label: '100%', nameKey: 'typography.scale_standard' },
  { value: '1.12', label: '112%', nameKey: 'typography.scale_editorial' },
  { value: '1.24', label: '124%', nameKey: 'typography.scale_large' },
] as const;

export default function TextScaleIsland({ lang = 'mk' }: { lang?: string }) {
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);
  const [scale, setScale] = useState('1');
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    // Load initial scale from localStorage
    let savedScale = '1';
    try {
      savedScale = localStorage.getItem('text-scale') || '1';
    } catch (e) {
      console.warn('localStorage not accessible:', e);
    }
    setScale(savedScale);
    document.documentElement.style.setProperty('--text-scale', savedScale);

    // Event listener to close dropdown when clicking outside
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleScaleChange = (value: string) => {
    setScale(value);
    setIsOpen(false);
    if (typeof document !== 'undefined') {
      document.documentElement.style.setProperty('--text-scale', value);
      try {
        localStorage.setItem('text-scale', value);
      } catch (e) {}
    }
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="header-utility-button h-9 w-9 flex items-center justify-center text-muted-foreground hover:text-foreground relative group"
        aria-label={t('typography.label')}
        aria-expanded={isOpen}
      >
        <Type size={18} className="transition-colors" />
        <span className="sr-only">{t('typography.label')}</span>
      </button>

      {isOpen && (
        <div 
          className="text-scale-menu absolute right-0 mt-2 w-52 max-w-[calc(100vw-2rem)] bg-popover text-popover-foreground border border-border shadow-lg z-[210] animate-in fade-in slide-in-from-top-2 duration-200"
          role="menu"
          aria-orientation="vertical"
        >
          <div className="py-1 px-1 divide-y divide-border/60">
            <div className="text-scale-menu-title px-3 py-2 text-[0.62rem] font-black tracking-widest text-muted-foreground uppercase">
              {t('typography.menu_title')}
            </div>
            <div className="py-1">
              {SCALES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => handleScaleChange(s.value)}
                  className={`text-scale-menu-item w-full text-left px-3 py-2.5 text-xs flex items-center justify-between transition-colors hover:bg-secondary ${
                    scale === s.value ? 'font-bold text-foreground' : 'text-muted-foreground'
                  }`}
                  role="menuitem"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-scale-menu-pct font-sans text-[0.68rem] tracking-wider font-extrabold text-muted-foreground/60">{s.label}</span>
                    <span className="text-scale-menu-name font-serif text-[0.8rem]">{t(s.nameKey)}</span>
                  </span>
                  {scale === s.value && <Check size={14} className="text-nyt-accent" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
