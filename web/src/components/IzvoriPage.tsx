import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { Search, Loader2, Info } from 'lucide-react';

interface Source {
  source: string;
  country: string;
  category: string;
}

export const IzvoriPage: React.FC = () => {
  const [sources, setSources] = useState<Source[]>([]);
  const [hotSources, setHotSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const [allRes, pulseRes] = await Promise.all([
          apiClient.getSources(),
          apiClient.getPulse()
        ]);
        
        if (!Array.isArray(allRes)) {
          console.error("API returned non-array for sources:", allRes);
          setError("Грешка при вчитување на податоците.");
          return;
        }

        // Deduplicate sources by name
        const unique = allRes.reduce((acc: Source[], curr: any) => {
          if (curr && curr.source && !acc.find(s => s.source === curr.source)) {
            acc.push(curr);
          }
          return acc;
        }, []);
        
        setSources(unique);
        
        if (Array.isArray(pulseRes)) {
          setHotSources(pulseRes.map((r: any) => r.source));
        }
      } catch (e: any) {
        console.error("Failed to load sources:", e);
        setError("Неуспешно поврзување со серверот.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filtered = sources.filter(s => 
    s.source?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const mkSources = filtered.filter(s => s.country === '🇲🇰' || !s.country || s.country === 'Македонија');
  const intSources = filtered.filter(s => s.country && s.country !== '🇲🇰' && s.country !== 'Македонија');

  return (
    <div className="bg-background text-foreground">
      <div className="site-layout py-8">
        <header className="mb-10 border-b-2 border-primary pb-8">
            <span className="nyt-section-label text-nyt-accent border border-nyt-accent px-2 py-0.5 mb-4 inline-block">ИМЕНИК</span>
            <h1 className="font-serif text-3xl md:text-5xl font-black leading-tight text-foreground mb-4">
                Медиумски Извори
            </h1>
            <div className="max-w-md mt-6 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Пребарај извори..."
                className="w-full bg-secondary border border-border pl-10 pr-4 py-2 text-sm text-foreground focus:outline-none focus:border-nyt-accent transition-colors rounded-full"
              />
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="lg:col-span-8">
            {loading ? (
              <div className="flex flex-col items-center py-20">
                <Loader2 className="animate-spin text-nyt-accent mb-4" size={32} />
                <p className="nyt-section-label text-muted-foreground">Вчитувам именик...</p>
              </div>
            ) : error ? (
              <div className="py-20 text-center border border-dashed border-nyt-red/30 bg-nyt-red/5">
                <p className="text-nyt-red font-serif italic mb-4">{error}</p>
                <button 
                  onClick={() => window.location.reload()}
                  className="nyt-section-label text-nyt-accent underline"
                >
                  Обидете се повторно
                </button>
              </div>
            ) : (
              <div className="space-y-12">
                <section>
                    <h2 className="nyt-section-label border-b border-foreground pb-2 mb-6">МАКЕДОНСКИ МЕДИУМИ</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                        {mkSources.map(s => (
                          <a 
                            key={s.source}
                            href={`/?q=${encodeURIComponent(s.source)}`}
                            className="font-serif font-bold text-sm text-foreground no-underline hover:text-nyt-accent flex items-center gap-2 py-1 border-b border-nyt-gray-200 text-left"
                          >
                              {s.source}
                              {hotSources.includes(s.source) && (
                                  <span className="text-[8px] bg-nyt-accent text-white px-1 rounded-sm animate-pulse">HOT</span>
                              )}
                          </a>
                        ))}
                        {mkSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                    </div>
                </section>

                <section>
                    <h2 className="nyt-section-label border-b border-foreground pb-2 mb-6">МЕЃУНАРОДНИ МЕДИУМИ</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                        {intSources.map(s => (
                          <a 
                            key={s.source}
                            href={`/?q=${encodeURIComponent(s.source)}`}
                            className="font-serif font-bold text-sm text-foreground no-underline hover:text-nyt-accent flex items-center gap-2 py-1 border-b border-nyt-gray-200 text-left"
                          >
                              {s.source}
                              <span className="nyt-section-label opacity-50 grayscale text-[10px]">{s.country}</span>
                          </a>
                        ))}
                        {intSources.length === 0 && <p className="text-muted-foreground text-xs italic">Нема пронајдени извори</p>}
                    </div>
                </section>
              </div>
            )}
          </div>

          <aside className="lg:col-span-4 space-y-10">
            <div className="border-t-2 border-primary pt-4">
                <h3 className="nyt-section-label flex items-center gap-2 mb-4"><Info size={14}/> ИНФОРМАЦИЈА</h3>
                <p className="font-serif text-sm italic leading-relaxed text-muted-foreground">
                    Пресек ги индексира само најрелевантните и најкредибилните извори. Листата постојано се ажурира врз основа на активноста на медиумите.
                </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default IzvoriPage;
