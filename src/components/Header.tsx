import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Search, Moon, Sun, X, BarChart3, BookOpen, Menu } from 'lucide-react';
import { useUIStore, useNewsStore } from '../store/useNewsStore';
import { apiClient } from '../api/client';
import { Weather } from '../types';

const CATEGORIES = [
  { label: 'МК', value: '🇲🇰' },
  { label: 'Балкан', value: 'Балкан' },
  { label: 'Европа', value: 'Европа' },
  { label: 'Германија', value: 'Германија' },
  { label: 'Америка', value: 'Америка' },
  { label: 'Свет', value: 'Свет' },
];

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedCategory, searchQuery, setSelectedCategory, setSearchQuery } = useUIStore();
  const { reset } = useNewsStore();
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains('dark')
  );
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [weather, setWeather] = useState<Weather | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const isHome = location.pathname === '/';

  useEffect(() => {
    apiClient.getWeather().then(setWeather).catch(() => {});
  }, []);

  useEffect(() => {
    if (searchOpen && searchRef.current) searchRef.current.focus();
  }, [searchOpen]);

  const toggleDark = () => {
    const html = document.documentElement;
    if (dark) {
      html.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    } else {
      html.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    }
    setDark(!dark);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput.trim());
    setSearchOpen(false);
    if (location.pathname !== '/') navigate('/');
  };

  const clearSearch = () => {
    setSearchInput('');
    setSearchQuery('');
    setSearchOpen(false);
  };

  const handleCategoryChange = (value: string) => {
    setSelectedCategory(value);
    reset();
    setMobileMenuOpen(false);
    if (location.pathname !== '/') navigate('/');
  };

  return (
    <header className="sticky top-0 z-50 bg-dark-0 dark:bg-dark-0 text-white shadow-lg">
      {/* Top bar */}
      <div className="page-container">
        <div className="flex items-center justify-between h-14 gap-3">
          {/* Logo */}
          <button
            onClick={() => { navigate('/'); clearSearch(); reset(); }}
            className="flex items-center gap-1.5 text-white hover:opacity-80 transition shrink-0"
          >
            <span className="text-2xl font-black tracking-tight leading-none select-none">
              ПРЕСЕК
            </span>
            <span className="text-brand-500 text-2xl font-black leading-none">.</span>
          </button>

          {/* Desktop category nav */}
          <nav className="hidden md:flex items-center gap-1 overflow-x-auto no-scrollbar flex-1 max-w-lg">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                onClick={() => handleCategoryChange(cat.value)}
                className={`px-3 py-1 rounded-full text-sm font-medium whitespace-nowrap transition ${
                  selectedCategory === cat.value
                    ? 'bg-brand-600 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-dark-3'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-1 shrink-0">
            {/* Weather */}
            {weather && (
              <span className="hidden lg:flex items-center gap-1 text-sm text-slate-400 mr-1">
                <span>{weather.icon}</span>
                <span>{weather.temp}°C</span>
              </span>
            )}

            {/* Search toggle */}
            {searchOpen ? (
              <form onSubmit={handleSearch} className="flex items-center gap-2">
                <input
                  ref={searchRef}
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Пребарај вести..."
                  className="bg-dark-2 border border-dark-3 text-white placeholder-slate-500 rounded-lg px-3 py-1.5 text-sm w-48 md:w-64 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                <button
                  type="button"
                  onClick={clearSearch}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
                >
                  <X size={18} />
                </button>
              </form>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
                title="Пребарај"
              >
                <Search size={18} />
              </button>
            )}

            {/* Dark mode toggle */}
            <button
              onClick={toggleDark}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
              title={dark ? 'Светол режим' : 'Темен режим'}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            {/* Nav links */}
            <button
              onClick={() => navigate('/briefing')}
              className="hidden md:flex p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
              title="Дневен преглед"
            >
              <BookOpen size={18} />
            </button>
            <button
              onClick={() => navigate('/stats')}
              className="hidden md:flex p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
              title="Статистика"
            >
              <BarChart3 size={18} />
            </button>

            {/* Mobile menu */}
            <button
              className="md:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-3 transition"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <Menu size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile nav */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-dark-3 bg-dark-1 px-4 py-3 flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.value}
              onClick={() => handleCategoryChange(cat.value)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition ${
                selectedCategory === cat.value
                  ? 'bg-brand-600 text-white'
                  : 'bg-dark-3 text-slate-400 hover:text-white'
              }`}
            >
              {cat.label}
            </button>
          ))}
          <button
            onClick={() => { navigate('/briefing'); setMobileMenuOpen(false); }}
            className="px-3 py-1 rounded-full text-sm bg-dark-3 text-slate-400 hover:text-white"
          >
            Преглед
          </button>
          <button
            onClick={() => { navigate('/stats'); setMobileMenuOpen(false); }}
            className="px-3 py-1 rounded-full text-sm bg-dark-3 text-slate-400 hover:text-white"
          >
            Статистика
          </button>
        </div>
      )}
    </header>
  );
};
