import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Command, Zap, TrendingUp, History } from 'lucide-react';

export default function SearchIsland() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = localStorage.getItem('presek_recent_searches');
    if (saved) setRecentSearches(JSON.parse(saved));

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
  }, [isOpen]);

  const handleSearch = (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    
    // Save to recent
    const newRecent = [searchQuery.trim(), ...recentSearches.filter(s => s !== searchQuery.trim())].slice(0, 5);
    setRecentSearches(newRecent);
    localStorage.setItem('presek_recent_searches', JSON.stringify(newRecent));
    
    window.location.href = `/?q=${encodeURIComponent(searchQuery.trim())}`;
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  return (
    <>
      <button 
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-3 px-4 py-2 bg-secondary/50 hover:bg-secondary border border-nyt rounded-full transition-all group"
        aria-label="Пребарај"
      >
        <Search size={16} className="text-muted group-hover:text-accent transition-colors" />
        <span className="text-[10px] font-black text-muted uppercase tracking-widest hidden sm:inline">Пребарај...</span>
        <span className="hidden lg:flex items-center gap-1 text-[9px] font-black text-muted/50 uppercase tracking-tighter ml-2 bg-primary/50 px-1.5 py-0.5 rounded border border-nyt">
          <Command size={8} /> K
        </span>
      </button>

      {/* Modern Search Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] bg-primary/80 backdrop-blur-xl flex flex-col items-center pt-24 px-4 transition-all duration-500 animate-in fade-in">
          <div className="w-full max-w-3xl relative">
            <button 
              onClick={() => setIsOpen(false)}
              className="absolute -top-16 right-0 p-3 text-muted hover:text-accent transition-colors hover:rotate-90 duration-300"
            >
              <X size={32} />
            </button>

            <form onSubmit={onSubmit} className="relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-accent to-primary opacity-20 blur group-focus-within:opacity-40 transition duration-1000 group-focus-within:duration-200 rounded-lg"></div>
              <div className="relative bg-primary border-2 border-nyt focus-within:border-accent transition-colors rounded-lg flex items-center p-2">
                <Search className="ml-4 text-muted group-focus-within:text-accent transition-colors" size={28} />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Што ве интересира денес?"
                  className="w-full bg-transparent py-4 px-6 text-2xl md:text-4xl font-serif font-bold text-primary outline-none placeholder:text-muted/30"
                />
                {query && (
                  <button type="button" onClick={() => setQuery('')} className="p-2 text-muted hover:text-primary">
                    <X size={20} />
                  </button>
                )}
                <button 
                  type="submit"
                  className="bg-accent text-white px-6 py-3 rounded-md font-black text-xs uppercase tracking-widest hover:brightness-110 transition-all mr-2 shadow-lg shadow-accent/20"
                >
                  Барај
                </button>
              </div>
              
              <div className="mt-4 flex items-center justify-between px-2">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-accent">
                    <Zap size={10} /> Semantic Search Active
                  </span>
                </div>
                <span className="text-[10px] text-muted italic opacity-50">
                  Пребарувајте според контекст и значење
                </span>
              </div>
            </form>

            <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-12">
              {recentSearches.length > 0 && (
                <div>
                  <h3 className="rail-label text-muted mb-6 flex items-center gap-2">
                    <History size={14} /> ПОСЛЕДНИ ПРЕБАРАУВАЊА
                  </h3>
                  <div className="space-y-2">
                    {recentSearches.map(s => (
                      <button 
                        key={s}
                        onClick={() => handleSearch(s)}
                        className="w-full flex items-center justify-between p-3 bg-secondary/30 hover:bg-secondary border border-transparent hover:border-nyt transition-all text-sm font-bold text-primary text-left group"
                      >
                        {s}
                        <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h3 className="rail-label text-muted mb-6 flex items-center gap-2">
                  <TrendingUp size={14} /> ПОПУЛАРНИ ТЕМИ
                </h3>
                <div className="flex flex-wrap gap-2">
                  {['Избори 2026', 'Економија', 'Технологија', 'Вештачка Интелигенција', 'Влада', 'ЕУ Интеграции'].map(tag => (
                    <button 
                      key={tag}
                      onClick={() => handleSearch(tag)}
                      className="px-4 py-2 bg-secondary/50 hover:bg-accent hover:text-white border border-nyt hover:border-accent transition-all rounded-sm text-[10px] font-black uppercase tracking-wider"
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ArrowRight({ size, className }: { size: number, className: string }) {
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="3" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      className={className}
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}
