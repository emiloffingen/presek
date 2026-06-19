import React, { useEffect, useState } from 'react';
import { useStore } from '@nanostores/react';
import { Moon, Sun } from 'lucide-react';
import { $theme, updateTheme } from '../lib/store';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';

function applyThemeToDocument(next: 'light' | 'dark') {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  if (next === 'dark') {
    root.classList.add('dark');
    root.style.colorScheme = 'dark';
  } else {
    root.classList.remove('dark');
    root.style.colorScheme = 'light';
  }

  const themeColor = next === 'dark' ? '#0b0d13' : '#fdfdfa';
  document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
    meta.setAttribute('content', themeColor);
  });
}

function readStoredTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';

  try {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light' || savedTheme === 'dark') {
      return savedTheme;
    }
  } catch (_) {}

  if (document.documentElement.classList.contains('dark')) {
    return 'dark';
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function ThemeIsland({ fixed = false, lang = 'sr' }: { fixed?: boolean; lang?: string }) {
  const theme = useStore($theme);
  const [ready, setReady] = useState(false);
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);

  useEffect(() => {
    const resolved = readStoredTheme();
    updateTheme(resolved);
    applyThemeToDocument(resolved);
    setReady(true);
  }, []);

  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light';
    updateTheme(next);
    applyThemeToDocument(next);
  };

  const baseClasses = 'header-utility-button theme-toggle-button flex items-center justify-center transition-all duration-300 group relative text-muted-foreground hover:text-foreground';
  const fixedClasses = 'fixed top-4 right-4 z-[200] h-10 w-10 border border-border bg-card shadow-sm hover:-translate-y-0.5 active:translate-y-0';
  const inlineClasses = 'h-9 w-9 shrink-0 hover:bg-secondary active:scale-95';

  const size = fixed ? 20 : 18;
  const activeTheme = ready ? theme : readStoredTheme();
  const Icon = activeTheme === 'dark' ? Moon : Sun;

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`${baseClasses} ${fixed ? fixedClasses : inlineClasses}`}
      aria-label={activeTheme === 'light' ? t('theme.to_dark') : t('theme.to_light')}
    >
      <Icon
        size={size}
        strokeWidth={2.25}
        className="theme-toggle-icon transition-colors"
        aria-hidden="true"
      />
    </button>
  );
}
