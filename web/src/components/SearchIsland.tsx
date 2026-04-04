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
        className="flex items-center gap-2 text-nyt-black hover:text-nyt-gray-600 transition-colors"
        aria-label="Пребарај"
      >
        <Search size={18} />
        <span className="text-[10px] font-black uppercase tracking-widest hidden sm:inline">Пребарај</span>
      </button>

      {/* NYT Style Search Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] bg-background flex flex-col items-center pt-12 px-4 transition-all animate-in fade-in duration-200">
          <div className="w-full max-w-4xl relative">
            <div className="flex justify-between items-center mb-12">
                <div className="flex items-center gap-2">
                    <img src="/img/presek_emblem.svg" alt="Logo" className="h-6 site-logo" />
                    <span className="font-serif font-black text-lg">ПРЕСЕК ПРЕБАРУВАЊЕ</span>
                </div>
                <button 
                onClick={() => setIsOpen(false)}
                className="p-2 text-nyt-black hover:bg-nyt-gray-100 transition-colors"
                >
                <X size={24} />
                </button>
            </div>

            <form onSubmit={onSubmit} className="mb-12">
              <div className="border-b-2 border-nyt-black flex items-center gap-4">
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Внесете клучни зборови..."
                  className="w-full bg-transparent py-4 text-3xl md:text-5xl font-serif font-black text-nyt-black outline-none placeholder:text-nyt-gray-300"
                />
                <button 
                  type="submit"
                  className="bg-nyt-black text-primary-foreground px-8 py-3 font-black text-xs uppercase tracking-widest hover:bg-nyt-gray-600 transition-all"
                >
                  Барај
                </button>
              </div>
              
              <div className="mt-4 flex items-center gap-2 text-[10px] font-black uppercase text-nyt-accent">
                <Zap size={10} /> Semantic search enabled — indexing 100,000+ Macedonian news articles
              </div>
            </form>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-16">
              {recentSearches.length > 0 && (
                <div>
                  <h3 className="font-sans text-[10px] font-black uppercase tracking-widest text-nyt-gray-500 mb-6 pb-2 border-b border-nyt-gray-200">
                    ПОСЛЕДНИ ПРЕБАРАУВАЊА
                  </h3>
                  <div className="space-y-4">
                    {recentSearches.map(s => (
                      <button 
                        key={s}
                        onClick={() => handleSearch(s)}
                        className="w-full text-left font-serif font-black text-xl text-nyt-black hover:text-nyt-accent transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h3 className="font-sans text-[10px] font-black uppercase tracking-widest text-nyt-gray-500 mb-6 pb-2 border-b border-nyt-gray-200">
                  АКТУЕЛНО
                </h3>
                <div className="flex flex-wrap gap-x-6 gap-y-4">
                  {['Влада', 'Економија', 'Избори', 'ЕУ Интеграции', 'Скопје', 'Технологија'].map(tag => (
                    <button 
                      key={tag}
                      onClick={() => handleSearch(tag)}
                      className="font-serif font-bold text-lg text-nyt-black hover:underline underline-offset-4 decoration-nyt-red"
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
