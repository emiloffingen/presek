import React, { useEffect } from 'react';
import { useStore } from '@nanostores/react';
import { Moon, Sun } from 'lucide-react';
import { $theme, updateTheme } from '../lib/store';

export default function ThemeIsland({ fixed = false }: { fixed?: boolean }) {
  const theme = useStore($theme);

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
        } else {
            root.classList.remove('dark');
        }

        // Update theme-color meta tags
        const lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
        const darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
        if (lightMeta) lightMeta.setAttribute('content', next === 'dark' ? '#000000' : '#fafafb');
        if (darkMeta) darkMeta.setAttribute('content', next === 'dark' ? '#000000' : '#1a1715');
    }
  };

  const baseClasses = "flex items-center justify-center transition-all duration-300 group relative";
  const fixedClasses = "fixed top-4 right-4 z-[200] h-10 w-10 rounded-full border border-border bg-secondary shadow-sm hover:scale-110 active:scale-95";
  const inlineClasses = "rounded-full p-2 hover:bg-secondary active:scale-90 transition-transform";

  const size = fixed ? 20 : 18;

  return (
    <button
      onClick={toggleTheme}
      className={`${baseClasses} ${fixed ? fixedClasses : inlineClasses}`}
      aria-label="Promeni tema"
    >
      <div className="relative" style={{ width: size, height: size }}>
        <div 
          className={`absolute inset-0 flex items-center justify-center transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            theme === 'light' ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-50 pointer-events-none'
          }`}
        >
          <Moon size={size} className="text-muted-foreground group-hover:text-foreground transition-colors" />
        </div>
        <div 
          className={`absolute inset-0 flex items-center justify-center transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            theme === 'dark' ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 rotate-90 scale-50 pointer-events-none'
          }`}
        >
          <Sun size={size} className="text-muted-foreground group-hover:text-foreground transition-colors" />
        </div>
      </div>
    </button>
  );
}
