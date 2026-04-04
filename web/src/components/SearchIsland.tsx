import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Command } from 'lucide-react';

export default function SearchIsland() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
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
  }, [isOpen]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    window.location.href = `/?q=${encodeURIComponent(query.trim())}`;
  };

  return (
    <>
      <button 
        onClick={() => setIsOpen(true)}
        className="p-2 hover:bg-secondary rounded-full transition-colors group flex items-center gap-2"
        aria-label="Пребарај"
      >
        <Search size={18} className="text-muted group-hover:text-primary" />
        <span className="hidden lg:inline text-[10px] font-black text-muted uppercase tracking-widest border border-color px-1.5 py-0.5 rounded">
          Ctrl K
        </span>
      </button>

      {/* Search Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] bg-primary/95 backdrop-blur-md flex flex-col items-center pt-24 px-4 transition-all duration-300">
          <div className="w-full max-w-2xl relative">
            <button 
              onClick={() => setIsOpen(false)}
              className="absolute -top-12 right-0 p-2 text-muted hover:text-primary transition-colors"
            >
              <X size={24} />
            </button>

            <form onSubmit={handleSearch} className="relative">
              <Search className="absolute left-0 top-1/2 -translate-y-1/2 text-muted" size={28} />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Што ве интересира денес?"
                className="w-full bg-transparent border-b-2 border-color focus:border-accent py-4 pl-12 pr-4 text-2xl md:text-4xl font-serif font-bold text-primary outline-none transition-colors"
              />
              <div className="mt-4 flex items-center gap-2 text-muted">
                <span className="text-[10px] font-black uppercase tracking-widest bg-secondary px-2 py-1 rounded">Semantic Search</span>
                <span className="text-xs italic">Пишувајте на природен јазик за попаметни резултати</span>
              </div>
            </form>

            <div className="mt-12">
              <h3 className="rail-label text-muted">Чести пребарувања</h3>
              <div className="flex flex-wrap gap-2 mt-4">
                {['Избори', 'Економија', 'Технологија', 'Вештачка Интелигенција'].map(tag => (
                  <button 
                    key={tag}
                    onClick={() => { setQuery(tag); window.location.href = `/?q=${encodeURIComponent(tag)}`; }}
                    className="px-4 py-2 bg-secondary hover:bg-accent hover:text-white transition-all rounded-sm text-xs font-bold uppercase tracking-wider"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
