import React, { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function ThemeIsland() {
  const [theme, setTheme] = useState<'light' | 'dark' | null>(null);

  useEffect(() => {
    // On mount, get the theme from localStorage or document class
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    const isDark = document.documentElement.classList.contains('dark');
    const initialTheme = savedTheme || (isDark ? 'dark' : 'light');
    setTheme(initialTheme);
  }, []);

  useEffect(() => {
    if (theme) {
      const root = document.documentElement;
      if (theme === 'dark') {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
      localStorage.setItem('theme', theme);
      
      // Sync theme color meta
      const meta = document.getElementById('themeMeta');
      if (meta) meta.setAttribute('content', theme === 'dark' ? '#0f1117' : '#FFFFFF');
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  if (theme === null) return <div className="p-2 w-9 h-9" />; // Placeholder during mount

  return (
    <button 
      onClick={toggleTheme}
      className="p-2 hover:bg-secondary rounded-full transition-colors group"
      aria-label="Промени тема"
    >
      {theme === 'light' ? (
        <Moon size={18} className="text-muted group-hover:text-primary" />
      ) : (
        <Sun size={18} className="text-muted group-hover:text-primary" />
      )}
    </button>
  );
}
