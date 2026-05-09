import React, { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function ThemeIsland({ fixed = false }: { fixed?: boolean }) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    if (typeof document === 'undefined') return;
    // Sync with actual class if it changed from OS or other script
    const isDark = document.documentElement.classList.contains('dark');
    const initialTheme = isDark ? 'dark' : 'light';
    setTheme(initialTheme);
    
    // Also check localStorage for user preference
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (savedTheme && savedTheme !== initialTheme) {
      setTheme(savedTheme);
    }
  }, []);

  const toggleTheme = () => {
    if (typeof document === 'undefined') return;
    setTheme(prev => {
      const next = prev === 'light' ? 'dark' : 'light';
      const root = document.documentElement;
      if (next === 'dark') {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
      
      // Update theme-color meta tags for immediate effect
      const lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
      const darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
      if (lightMeta) lightMeta.setAttribute('content', next === 'dark' ? '#000000' : '#fafafb');
      if (darkMeta) darkMeta.setAttribute('content', next === 'dark' ? '#000000' : '#1a1715');

      localStorage.setItem('theme', next);
      return next;
    });
  };



  const baseClasses = "flex items-center justify-center transition-all duration-300 group";
  const fixedClasses = "fixed top-4 right-4 z-[200] h-10 w-10 rounded-full border border-border bg-secondary shadow-sm hover:scale-110";
  const inlineClasses = "rounded-full p-2 hover:bg-secondary";

  return (
    <button 
      onClick={toggleTheme}
      className={`${baseClasses} ${fixed ? fixedClasses : inlineClasses}`}
      aria-label="Промени тема"
    >
      <div className={`relative transition-transform duration-500 ${theme === 'dark' ? 'rotate-[360deg]' : 'rotate-0'}`}>
        {theme === 'light' ? (
          <Moon size={fixed ? 20 : 18} className="text-muted-foreground group-hover:text-foreground transition-transform duration-300 hover:scale-110" />
        ) : (
          <Sun size={fixed ? 20 : 18} className="text-muted-foreground group-hover:text-foreground transition-transform duration-300 hover:scale-110" />
        )}
      </div>
    </button>
  );
}
