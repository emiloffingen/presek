import React, { useState, useEffect, useRef } from 'react';
import { Type, Check } from 'lucide-react';

const SCALES = [
  { value: '1', label: '100%', name: 'Standard' },
  { value: '1.12', label: '112%', name: 'Editorial' },
  { value: '1.24', label: '124%', name: 'Poveќano' }
];

export default function TextScaleIsland() {
  const [scale, setScale] = useState('1');
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    // Load initial scale from localStorage
    const savedScale = localStorage.getItem('text-scale') || '1';
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
      localStorage.setItem('text-scale', value);
    }
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="rounded-full p-2 hover:bg-secondary active:scale-90 transition-transform flex items-center justify-center text-muted-foreground hover:text-foreground relative group"
        aria-label="Skaliraj golemina na tekst"
        aria-expanded={isOpen}
      >
        <Type size={18} className="transition-colors" />
        <span className="sr-only">Typography</span>
      </button>

      {isOpen && (
        <div 
          className="absolute right-0 mt-2 w-48 bg-card border border-border rounded-none shadow-lg z-[210] animate-in fade-in slide-in-from-top-2 duration-200"
          role="menu"
          aria-orientation="vertical"
        >
          <div className="py-1 px-1 divide-y divide-border/60">
            <div className="px-3 py-2 text-[0.62rem] font-black tracking-widest text-muted-foreground uppercase">
              Tipografija
            </div>
            <div className="py-1">
              {SCALES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => handleScaleChange(s.value)}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between transition-colors hover:bg-secondary ${
                    scale === s.value ? 'font-bold text-foreground' : 'text-muted-foreground'
                  }`}
                  role="menuitem"
                >
                  <span className="flex items-center gap-2">
                    <span className="font-sans text-[0.68rem] tracking-wider font-extrabold text-muted-foreground/60">{s.label}</span>
                    <span className="font-serif text-[0.8rem]">{s.name}</span>
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
