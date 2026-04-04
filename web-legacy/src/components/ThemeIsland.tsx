import React, { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function ThemeIsland() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('theme')) {
      return localStorage.getItem('theme') as 'light' | 'dark';
    }
    return 'dark';
  });

  useEffect(() => {
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
  }, [theme]);

  return (
    <button 
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
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
