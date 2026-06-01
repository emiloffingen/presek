import React, { useEffect } from 'react';
import { useStore } from '@nanostores/react';
import { Moon, Sun } from 'lucide-react';
import { $theme, updateTheme } from '../lib/store';
import { useTranslations } from '../i18n/utils';

export default function ThemeIsland({ fixed = false, lang = 'sr' }: { fixed?: boolean; lang?: string }) {
  const theme = useStore($theme);
  const t = useTranslations(lang as any);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    
    // Initial sync with localStorage
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (savedTheme) {
      updateTheme(savedTheme);
    } else {
        const isDark = document.documentElement.classList.contains('dark');
        updateTheme(isDark ? 'dark' : 'light');
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light';
    updateTheme(next);

    if (typeof document !== 'undefined') {
        const root = document.documentElement;
        if (next === 'dark') {
            root.classList.add('dark');
            root.style.colorScheme = 'dark';
        } else {
            root.classList.remove('dark');
            root.style.colorScheme = 'light';
        }

        // Update theme-color meta tags
        const lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
        const darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
        const themeColor = next === 'dark' ? '#0b0d13' : '#fdfdfa';
        if (lightMeta) lightMeta.setAttribute('content', themeColor);
        if (darkMeta) darkMeta.setAttribute('content', themeColor);
    }
  };

  const baseClasses = "header-utility-button flex items-center justify-center transition-all duration-300 group relative";
  const fixedClasses = "fixed top-4 right-4 z-[200] h-10 w-10 border border-border bg-card shadow-sm hover:-translate-y-0.5 active:translate-y-0";
  const inlineClasses = "h-9 w-9 hover:bg-secondary active:scale-95";

  const size = fixed ? 20 : 18;

  return (
    <button
      onClick={toggleTheme}
      className={`${baseClasses} ${fixed ? fixedClasses : inlineClasses}`}
      aria-label={theme === 'light' ? t('theme.to_dark') : t('theme.to_light')}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <div 
          className={`absolute inset-0 flex items-center justify-center transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            theme === 'light' ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-50 pointer-events-none'
          }`}
        >
          <Sun size={size} className="text-muted-foreground group-hover:text-foreground transition-colors" />
        </div>
        <div 
          className={`absolute inset-0 flex items-center justify-center transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            theme === 'dark' ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 rotate-90 scale-50 pointer-events-none'
          }`}
        >
          <Moon size={size} className="text-muted-foreground group-hover:text-foreground transition-colors" />
        </div>
      </div>
    </button>
  );
}
