import React, { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function ThemeIsland({ fixed = false }: { fixed?: boolean }) {
  const [theme, setTheme] = useState<'light' | 'dark' | null>(null);

  useEffect(() => {
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
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  if (theme === null) return <div className="p-2 w-9 h-9" />;

  const baseClasses = "flex items-center justify-center transition-all duration-300 group";
  const fixedClasses = "fixed top-4 right-4 z-[200] w-10 h-10 bg-secondary border border-nyt-gray-300 shadow-sm rounded-full hover:scale-110";
  const inlineClasses = "p-2 hover:bg-secondary rounded-full";

  return (
    <button 
      onClick={toggleTheme}
      className={`${baseClasses} ${fixed ? fixedClasses : inlineClasses}`}
      aria-label="Промени тема"
    >
      {theme === 'light' ? (
        <Moon size={fixed ? 20 : 18} className="text-nyt-gray-600 group-hover:text-nyt-black" />
      ) : (
        <Sun size={fixed ? 20 : 18} className="text-nyt-gray-600 group-hover:text-nyt-black" />
      )}
    </button>
  );
}
