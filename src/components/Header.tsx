import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Search, Moon, Sun, X, Menu } from 'lucide-react';
import { useUIStore, useNewsStore } from '../store/useNewsStore';
import { apiClient } from '../api/client';
import { Weather } from '../types';

const CATEGORIES = [
  { label: 'Сите', value: '' },
  { label: 'Македонија', value: 'Македонија' },
  { label: 'Балкан', value: 'Балкан' },
  { label: 'Европа', value: 'Европа' },
  { label: 'Свет', value: 'Свет' },
  { label: 'Економија', value: 'Економија' },
  { label: 'Спорт', value: 'Спорт' },
  { label: 'Технологија', value: 'Технологија' },
];

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedCategory, setSelectedCategory, setSearchQuery } = useUIStore();
  const { reset } = useNewsStore();
  
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [weather, setWeather] = useState<Weather | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [currentDate, setCurrentDate] = useState('');

  useEffect(() => {
    apiClient.getWeather().then(setWeather).catch(() => {});
    
    const now = new Date();
    const options: Intl.DateTimeFormatOptions = { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    };
    setCurrentDate(now.toLocaleDateString('mk-MK', options));
  }, []);

  const toggleDark = () => {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    document.cookie = `theme=${isDark ? 'dark' : 'light'}; path=/; max-age=31536000; SameSite=Lax`;
    setDark(isDark);
    
    const meta = document.getElementById('themeMeta');
    if (meta) meta.setAttribute('content', isDark ? '#0f1117' : '#FFFFFF');
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput.trim());
    setSearchOpen(false);
    if (location.pathname !== '/') navigate('/');
  };

  const handleCategoryChange = (value: string) => {
    setSelectedCategory(value);
    reset();
    setMobileMenuOpen(false);
    if (location.pathname !== '/') navigate('/');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <>
      {/* Unified NYT Masthead Bar */}
      <div className="utility-bar">
        <div className="utility-inner">
          <div className="flex flex-col gap-[2px]">
            <span className="font-extrabold text-[0.65rem] uppercase tracking-wider text-primary">
              {currentDate || '...'}
            </span>
            <span className="text-[0.6rem] text-muted uppercase tracking-wider">Скопје, Македонија</span>
          </div>

          <div className="ml-10 hidden sm:flex gap-5 text-[0.65rem] font-bold uppercase text-muted min-w-[130px]">
            <span className="inline-block min-w-[45px]">{weather ? `${weather.temp}°C` : ''}</span>
            <span className="inline-block min-w-[60px]">{weather?.aqi != null ? `AQI: ${weather.aqi}` : ''}</span>
          </div>

          <div className="ml-auto flex gap-6 items-center">
            <button onClick={() => navigate('/briefing')} className="font-extrabold text-[0.65rem] uppercase tracking-wider text-primary hover:opacity-70 transition">Дневен Брифинг</button>
            <button onClick={() => navigate('/stats')} className="font-extrabold text-[0.65rem] uppercase tracking-wider text-primary hover:opacity-70 transition">Статистика</button>
          </div>
        </div>
      </div>

      <header className="site-header">
        <div className="text-center py-8 relative">
          <button 
            className="icon-btn absolute left-0 top-1/2 -translate-y-1/2 lg:hidden"
            onClick={() => setMobileMenuOpen(true)}
          >
            <Menu size={20} />
          </button>
          
          <button onClick={() => { navigate('/'); setSelectedCategory(''); reset(); }} className="inline-block hover:opacity-90 transition">
            <img src="/static/logo.svg" alt="Presek" className="h-16" />
          </button>
        </div>

        <nav className="hidden lg:block">
          <div className="nav-inner-broadsheet">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                onClick={() => handleCategoryChange(cat.value)}
                className={`cat-btn ${selectedCategory === cat.value ? 'active' : ''}`}
              >
                {cat.label}
              </button>
            ))}
          </div>
          
          <div className="flex justify-center mt-2 gap-4">
            <button className="icon-btn" onClick={() => setSearchOpen(true)}>
              <Search size={18} />
            </button>
            <button className="icon-btn" onClick={toggleDark}>
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </nav>
      </header>

      {/* Mobile Drawer */}
      <div className={`mobile-drawer-overlay ${mobileMenuOpen ? 'active' : ''}`} onClick={() => setMobileMenuOpen(false)} />
      <div className={`mobile-drawer ${mobileMenuOpen ? 'open' : ''}`}>
        <div className="drawer-header">
          <span className="drawer-logo">Пресек</span>
          <button className="icon-btn" onClick={() => setMobileMenuOpen(false)}>
            <X size={22} />
          </button>
        </div>
        <nav className="drawer-nav">
          <div className="mb-8 border-b border-color pb-6">
            <h3 className="rail-label ml-4 mb-2">ТЕМУ</h3>
            {CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                onClick={() => handleCategoryChange(cat.value)}
                className={`cat-btn block w-full text-left px-6 py-3 ${selectedCategory === cat.value ? 'active' : ''}`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <h3 className="rail-label ml-4 mb-2">ИЗБОР</h3>
          <button onClick={() => { navigate('/briefing'); setMobileMenuOpen(false); }} className="flex items-center gap-3 px-6 py-3 text-primary font-bold"><span className="text-lg">☕</span> Дневен Брифинг</button>
          <button onClick={() => { navigate('/saved'); setMobileMenuOpen(false); }} className="flex items-center gap-3 px-6 py-3 text-primary font-bold"><span className="text-lg">🔖</span> Зачувани</button>
          <button onClick={() => { navigate('/stats'); setMobileMenuOpen(false); }} className="flex items-center gap-3 px-6 py-3 text-primary font-bold"><span className="text-lg">📊</span> Медиумски Пулс</button>
          <button onClick={() => { navigate('/arhiva'); setMobileMenuOpen(false); }} className="flex items-center gap-3 px-6 py-3 text-primary font-bold"><span className="text-lg">📅</span> Архива</button>
          <button onClick={() => { navigate('/izvori'); setMobileMenuOpen(false); }} className="flex items-center gap-3 px-6 py-3 text-primary font-bold"><span className="text-lg">🔗</span> Извори</button>
          
          <div className="mt-4 px-6">
            <button className="btn-outline w-full justify-start gap-3" onClick={toggleDark}>
              {dark ? <Sun size={18} /> : <Moon size={18} />}
              {dark ? 'Светол режим' : 'Темен режим'}
            </button>
          </div>
        </nav>
      </div>

      {/* Search Overlay */}
      <div className={`search-overlay ${searchOpen ? 'active' : ''}`}>
        <div className="w-full max-w-2xl px-4">
          <form onSubmit={handleSearch} className="flex items-center gap-4 border-b-2 border-primary pb-2">
            <Search size={24} className="text-muted" />
            <input
              autoFocus
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Пребарајте вести..."
              className="bg-transparent border-none text-2xl w-full focus:outline-none text-primary"
            />
            <button type="button" onClick={() => setSearchOpen(false)} className="icon-btn">
              <X size={24} />
            </button>
          </form>
        </div>
      </div>
    </>
  );
};
