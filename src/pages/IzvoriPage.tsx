import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { Header } from '../components/Header';
import { Search, Loader2, Info } from 'lucide-react';

interface Source {
  name: string;
  country: string;
  category: string;
}

export const IzvoriPage: React.FC = () => {
  const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>(() => window.__INITIAL_SOURCES_DATA__?.sources || []);
  const [hotSources, setHotSources] = useState<string[]>(() => window.__INITIAL_SOURCES_DATA__?.hot_sources || []);
  const [loading, setLoading] = useState(sources.length === 0);
  const [searchTerm, setSearchTerm] = useState('');
  const hydrated = useRef(sources.length > 0);

  useEffect(() => {
    if (hydrated.current) return;

    const load = async () => {
      try {
        const [allRes, pulseRes] = await Promise.all([
          apiClient.getSources(), // Assuming this exists or using fetch
          fetch('/api/sources/pulse').then(r => r.json())
        ]);
        setSources(allRes);
        setHotSources(pulseRes.map((r: any) => r.source));
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
        hydrated.current = true;
      }
    };
    load();
  }, []);

  const filtered = sources.filter(s => 
    s.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const mkSources = filtered.filter(s => s.country === '🇲🇰');
  const intSources = filtered.filter(s => s.country !== '🇲🇰');

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        <header className="mb-10 border-b-2 border-primary pb-8">
            <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5 mb-4 inline-block">ИМЕНИК</span>
            <h1 className="font-serif text-3xl md:text-5xl font-bold leading-tight text-primary mb-4">
                Медиумски Извори
            </h1>
            <div className="max-w-md mt-6 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={16} />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Пребарај извори..."
                className="w-full bg-secondary border border-color pl-10 pr-4 py-2 text-sm text-primary focus:outline-none focus:border-accent transition-colors rounded-full"
              />
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="lg:col-span-8">
            {loading ? (
              <div className="flex flex-col items-center py-20">
                <Loader2 className="animate-spin text-accent mb-4" size={32} />
                <p className="text-muted font-bold uppercase tracking-widest text-xs">Вчитувам именик...</p>
              </div>
            ) : (
              <div className="space-y-12">
                <section>
                    <h2 className="rail-label mb-6">МАКЕДОНСКИ МЕДИУМИ</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                        {mkSources.map(s => (
                          <button 
                            key={s.name}
                            onClick={() => {
                              // We can navigate to search with this source
                              navigate(`/?q=${encodeURIComponent(s.name)}`);
                            }}
                            className="text-xs font-bold text-primary no-underline hover:text-accent flex items-center gap-2 py-1 border-b border-color text-left"
                          >
                              {s.name}
                              {hotSources.includes(s.name) && (
                                  <span className="text-[8px] bg-accent text-white px-1 rounded-sm animate-pulse">HOT</span>
                              )}
                          </button>
                        ))}
                        {mkSources.length === 0 && <p className="text-muted text-xs italic">Нема пронајдени извори</p>}
                    </div>
                </section>

                <section>
                    <h2 className="rail-label mb-6">МЕЃУНАРОДНИ МЕДИУМИ</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                        {intSources.map(s => (
                          <button 
                            key={s.name}
                            onClick={() => navigate(`/?q=${encodeURIComponent(s.name)}`)}
                            className="text-xs font-bold text-primary no-underline hover:text-accent flex items-center gap-2 py-1 border-b border-color text-left"
                          >
                              {s.name}
                              <span className="opacity-50 grayscale">{s.country}</span>
                          </button>
                        ))}
                        {intSources.length === 0 && <p className="text-muted text-xs italic">Нема пронајдени извори</p>}
                    </div>
                </section>
              </div>
            )}
          </div>

          <aside className="lg:col-span-4 space-y-10">
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label flex items-center gap-2"><Info size={14}/> ИНФОРМАЦИЈА</h3>
                <p className="text-[11px] leading-relaxed text-muted italic">
                    Пресек ги индексира само најрелевантните и најкредибилните извори. Листата постојано се ажурира врз основа на активноста на медиумите.
                </p>
            </div>
            
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label">СТАТИСТИКА</h3>
                <div className="bg-secondary p-4">
                  <p className="text-[10px] font-bold text-muted uppercase mb-1">Вкупно извори</p>
                  <p className="text-2xl font-serif font-bold text-primary">{sources.length}</p>
                </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};
