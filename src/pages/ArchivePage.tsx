import React, { useState, useEffect, useRef } from 'react';
import { Header } from '../components/Header';
import { apiClient } from '../api/client';
import { Loader2, Calendar, Info } from 'lucide-react';

export const ArchivePage: React.FC = () => {
  const [data, setData] = useState<any>(() => window.__INITIAL_ARCHIVE_DATA__);
  const [date, setDate] = useState(data?.date || new Date().toISOString().split('T')[0]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(!data);
  const hydrated = useRef(!!data);

  const fetchArchive = async (d: string, p: number) => {
    setLoading(true);
    try {
      const res = await apiClient.getArchive({ date: d, page: p, page_size: 50 });
      setData(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (hydrated.current && data?.date === date) return;
    fetchArchive(date, page);
    hydrated.current = true;
  }, [date, page]);

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        <header className="mb-10 border-b-2 border-primary pb-8">
            <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5 mb-4 inline-block">АРХИВА</span>
            <h1 className="font-serif text-3xl md:text-5xl font-bold leading-tight text-primary mb-4">
                Архива на вести
            </h1>
            <div className="flex flex-wrap items-center gap-6 mt-6">
                <div className="flex items-center gap-3">
                    <span className="text-[10px] font-black uppercase text-muted">Избери датум:</span>
                    <div className="relative">
                      <input 
                        type="date" 
                        value={date}
                        onChange={(e) => { setDate(e.target.value); setPage(0); }}
                        className="bg-secondary border border-color px-3 py-1 text-xs font-bold text-primary focus:outline-none focus:border-accent"
                      />
                    </div>
                </div>
                {data && (
                <div className="flex items-center gap-4 text-[10px] font-black uppercase text-muted">
                    <span>{data.total} вести</span>
                    <span>·</span>
                    <span>{data.sources} извори</span>
                </div>
                )}
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="lg:col-span-8">
            {loading && !data ? (
              <div className="flex flex-col items-center py-20">
                <Loader2 className="animate-spin text-accent mb-4" size={32} />
                <p className="text-muted font-bold uppercase tracking-widest text-xs">Вчитувам архива...</p>
              </div>
            ) : (
              <div id="archive-list">
                {data?.articles?.length > 0 ? (
                  <>
                    <div className="space-y-1">
                        {data.articles.map((a: any) => (
                        <a key={a.id} href={a.link} target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 py-3 border-b border-color no-underline group">
                            <span className="text-[10px] font-bold text-muted tabular-nums w-10 shrink-0">
                              {new Date(a.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                            <span className="text-[10px] font-black uppercase text-accent w-24 shrink-0 truncate">{a.source}</span>
                            <span className="text-sm font-serif font-bold text-primary group-hover:text-accent transition-colors leading-tight">{a.title}</span>
                            <span className="ml-auto text-muted group-hover:text-accent transition-colors text-xs">↗</span>
                        </a>
                        ))}
                    </div>
                    
                    <div className="flex justify-between items-center mt-10 py-6 border-t border-color">
                      <button 
                        disabled={page === 0 || loading}
                        onClick={() => setPage(p => p - 1)}
                        className="text-[10px] font-black uppercase text-primary hover:text-accent disabled:opacity-30 transition-colors"
                      >
                        ← Претходна
                      </button>
                      <span className="text-[10px] font-black uppercase text-muted">Страна {page + 1}</span>
                      <button 
                        disabled={!data.has_more || loading}
                        onClick={() => setPage(p => p + 1)}
                        className="text-[10px] font-black uppercase text-primary hover:text-accent disabled:opacity-30 transition-colors"
                      >
                        Следна →
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="py-20 text-center bg-secondary">
                      <p className="text-muted text-sm font-bold uppercase">НЕМА ПРОНАЈДЕНИ ВЕСТИ ЗА ОВОЈ ДАТУМ</p>
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="lg:col-span-4 space-y-10">
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label flex items-center gap-2"><Info size={14}/> ИНФОРМАЦИЈА</h3>
                <p className="text-[11px] leading-relaxed text-muted italic">
                    Архивата ги содржи сите индексирани вести во последните 30 дена. Користете го календарот за пребарување по специфичен датум.
                </p>
            </div>
            
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label">ПОПУЛАРНИ ТЕМИ</h3>
                <div className="bg-secondary p-4">
                  <p className="text-[10px] font-bold text-muted uppercase leading-relaxed">
                    Пребарувајте низ архивата за да ги откриете трендовите кои го обликуваа изминатиот период.
                  </p>
                </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};
