import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Flame, Sparkles, Newspaper, Link2,
  MessageCircle, Loader2, Clock, Tag, Send, Activity,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ClusterDetail } from '../types';
import { Header } from '../components/Header';

export const ClusterDetailPage: React.FC = () => {
  const { clusterId } = useParams<{ clusterId: string }>();
  const navigate = useNavigate();
  const [cluster, setCluster] = useState<ClusterDetail | null>(() => {
    const initial = window.__INITIAL_CLUSTER_DATA__;
    if (initial && initial.cluster?.cluster_id === clusterId) {
      return initial.cluster;
    }
    return null;
  });
  const [loading, setLoading] = useState(!cluster);
  const [error, setError] = useState<string | null>(null);
  const [chatQuery, setChatQuery] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResponse, setChatResponse] = useState<string | null>(null);
  const hydrated = useRef(!!cluster);

  useEffect(() => {
    if (!clusterId) return;
    if (hydrated.current && cluster?.cluster_id === clusterId) return;

    setLoading(true);
    apiClient.getClusterDetail(clusterId)
      .then((res) => { setCluster(res.data); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Грешка'))
      .finally(() => {
        setLoading(false);
        hydrated.current = true;
      });
  }, [clusterId]);

  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatQuery.trim() || !clusterId) return;
    setChatLoading(true);
    try {
      const res = await apiClient.chatCluster(clusterId, chatQuery);
      setChatResponse(res.response);
    } catch {
      setChatResponse('Грешка при обработката. Обидете се повторно.');
    } finally {
      setChatLoading(false);
    }
  };

  if (loading && !cluster) {
    return (
      <div className="min-h-screen bg-primary">
        <Header />
        <div className="page-container py-12 flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-accent" />
          <p className="text-muted">Вчитување анализа...</p>
        </div>
      </div>
    );
  }

  if (error || !cluster) {
    return (
      <div className="min-h-screen bg-primary">
        <Header />
        <div className="page-container py-12 text-center">
          <p className="text-accent mb-4">{error || 'Кластерот не е пронајден'}</p>
          <button onClick={() => navigate('/')} className="btn-primary">
            <ArrowLeft size={16} />
            Назад на почетна
          </button>
        </div>
      </div>
    );
  }

  const article = cluster.articles[0];

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        <header className="mb-10 border-b-2 border-primary pb-8">
            <div className="flex flex-wrap gap-2 mb-4">
                {(cluster.is_breaking || cluster.articles.length > 5) && (
                    <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5">BREAKING</span>
                )}
                {cluster.has_synthesis && (
                    <span className="text-[10px] font-black uppercase tracking-widest text-white bg-accent px-2 py-0.5">СУБЛИМАТ</span>
                )}
                {cluster.has_fact_check && (
                    <span className="text-[10px] font-black uppercase tracking-widest text-white bg-blue-600 px-2 py-0.5">FACT CHECK</span>
                )}
            </div>
            <h1 className="font-serif text-3xl md:text-5xl font-bold leading-tight text-primary mb-4">
                {article.title}
            </h1>
            <div className="flex items-center gap-4 text-xs font-bold uppercase text-muted">
                <span className="flex items-center gap-1"><Clock size={12}/> {new Date(article.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}</span>
                <span>·</span>
                <span>{cluster.total_reading_time || 1} мин читање</span>
                <span>·</span>
                <span>{cluster.articles.length} извори</span>
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <div className="lg:col-span-8">
                {cluster.generated_article && (
                    <section className="mb-12">
                        <h2 className="rail-label mb-6 flex items-center gap-2 text-accent"><Sparkles size={14}/> ВОДЕЧКА СТОРИЈА</h2>
                        <div className="prose-nyt text-xl leading-relaxed text-secondary font-serif">
                            {cluster.generated_article.split('\n').filter(p => p.trim()).map((paragraph, idx) => (
                                <p key={idx} className={`mb-6 last:mb-0 ${idx === 0 ? "first-letter:text-5xl first-letter:font-black first-letter:mr-3 first-letter:float-left first-letter:leading-[1] first-letter:text-accent" : ""}`}>
                                    {paragraph}
                                </p>
                            ))}
                        </div>
                        <div className="h-px bg-color my-10" />
                    </section>
                )}

                {cluster.has_synthesis && cluster.synthesis && (
                    <section className="mb-12">
                        <h2 className="rail-label mb-6 flex items-center gap-2"><Sparkles size={14}/> ПРЕСЕК СУБЛИМАТ</h2>
                        <div className="article-prose text-lg leading-relaxed italic border-l-4 border-accent pl-6 py-2 text-secondary whitespace-pre-line">
                            {cluster.synthesis}
                        </div>
                        
                        {cluster.perspectives && cluster.perspectives.length > 0 && (
                            <div className="mt-10 grid gap-6">
                                <p className="section-heading">РАЗЛИЧНИ ПЕРСПЕКТИВИ</p>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {cluster.perspectives.map((p, i) => (
                                        <div key={i} className="bg-secondary p-5 border-t border-color">
                                            <p className="font-bold text-sm mb-2 uppercase tracking-tight text-primary">{p.angle}</p>
                                            <p className="text-sm text-secondary leading-relaxed">{p.content}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </section>
                )}

                {cluster.timeline && cluster.timeline.length > 1 && (
                    <section className="mb-12 bg-secondary p-8 border border-color">
                        <h2 className="rail-label mb-8 flex items-center gap-2"><Clock size={14}/> ХРОНОЛОГИЈА НА НАСТАНОТ</h2>
                        <div className="space-y-8 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-color">
                            {cluster.timeline.map((entry, idx) => (
                                <div key={entry.article_id} className="relative pl-10">
                                    <div className={`absolute left-0 top-1.5 w-4.5 h-4.5 rounded-full border-2 bg-primary ${entry.is_major ? 'border-accent scale-110' : 'border-color'}`} />
                                    <div className="flex flex-col gap-1">
                                        <div className="flex items-center gap-3">
                                            <span className="text-[10px] font-black uppercase text-accent">{entry.source}</span>
                                            <span className="text-[10px] font-bold text-muted">{new Date(entry.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}</span>
                                        </div>
                                        <h3 className={`font-serif leading-tight ${entry.is_major ? 'text-lg font-bold text-primary' : 'text-base text-secondary'}`}>
                                            {entry.title}
                                        </h3>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                <section>
                    <h2 className="rail-label mb-6 flex items-center gap-2"><Newspaper size={14}/> СИТЕ ИЗВОРИ</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {cluster.articles.map((art) => (
                            <div key={art.id} className="border-b border-color pb-4">
                                <div className="flex justify-between items-start gap-3 mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] font-black uppercase text-accent">{art.source}</span>
                                        {art.is_fact_check && (
                                            <span className="text-[9px] font-bold text-white bg-blue-600 px-1">FACT CHECK</span>
                                        )}
                                    </div>
                                    <span className="text-[10px] text-muted">
                                        {new Date(art.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}
                                    </span>
                                </div>
                                <a href={art.link} target="_blank" rel="noopener noreferrer" className="font-serif font-bold text-base text-primary no-underline hover:text-accent transition-colors block leading-snug">
                                    {art.title}
                                </a>
                            </div>
                        ))}
                    </div>
                </section>
            </div>

            <aside className="lg:col-span-4 space-y-10">
                {/* Sentiment / Media Pulse */}
                {cluster.sentiment && (
                    <div className="rail-widget border-t-2 border-primary">
                        <h3 className="rail-label flex items-center gap-2"><Activity size={14}/> МЕДИУМСКИ ПУЛС</h3>
                        <div className="bg-secondary p-5">
                            <div className="flex items-end gap-1 mb-4 h-12">
                                {cluster.sentiment.tone_analysis && (
                                    <>
                                        <div className="flex-1 bg-accent/20 relative group" style={{ height: `${(cluster.sentiment.tone_analysis.sensationalism || 0) * 100}%` }}>
                                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-primary text-[10px] p-1 border border-color opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">Сензационализам</div>
                                        </div>
                                        <div className="flex-1 bg-green-500/20 relative group" style={{ height: `${(cluster.sentiment.tone_analysis.objectivity || 0) * 100}%` }}>
                                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-primary text-[10px] p-1 border border-color opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">Објективност</div>
                                        </div>
                                        <div className="flex-1 bg-red-500/20 relative group" style={{ height: `${(cluster.sentiment.tone_analysis.emotional_charge || 0) * 100}%` }}>
                                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-primary text-[10px] p-1 border border-color opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">Емотивност</div>
                                        </div>
                                    </>
                                )}
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-[10px] font-black uppercase text-muted">Тон на известување</span>
                                <span className="text-xs font-bold text-primary uppercase">{cluster.sentiment.label || 'Неутрален'}</span>
                            </div>
                            <div className="mt-2 w-full h-1.5 bg-primary overflow-hidden border border-color">
                                <div 
                                    className={`h-full transition-all duration-1000 ${cluster.sentiment.score > 0.2 ? 'bg-green-500' : cluster.sentiment.score < -0.2 ? 'bg-nyt-red' : 'bg-accent'}`}
                                    style={{ 
                                        width: `${((cluster.sentiment.score + 1) / 2) * 100}%`,
                                        marginLeft: '0%' 
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                )}

                {/* AI Chat */}
                <div className="rail-widget border-t-2 border-primary">
                    <h3 className="rail-label flex items-center gap-2"><MessageCircle size={14}/> ПРАШАЈ ГО ПРЕСЕК</h3>
                    <div className="bg-secondary p-5">
                        <form onSubmit={handleChat} className="space-y-4">
                            <textarea
                                value={chatQuery}
                                onChange={(e) => setChatQuery(e.target.value)}
                                placeholder="Прашај нешто за овие вести..."
                                rows={3}
                                className="w-full bg-primary border border-color p-3 text-sm text-primary focus:outline-none focus:border-accent transition-colors resize-none"
                            />
                            <button
                                type="submit"
                                disabled={chatLoading || !chatQuery.trim()}
                                className="w-full bg-primary border-2 border-primary py-2 text-[10px] font-black uppercase tracking-widest hover:bg-primary/10 transition-colors disabled:opacity-50"
                            >
                                {chatLoading ? 'Обработка...' : 'Испрати прашање'}
                            </button>
                        </form>
                        {chatResponse && (
                            <div className="mt-4 p-4 bg-primary border-l-2 border-accent text-xs leading-relaxed text-secondary italic">
                                {chatResponse}
                            </div>
                        )}
                    </div>
                </div>

                {/* Tags */}
                {cluster.tags && cluster.tags.length > 0 && (
                  <div className="rail-widget border-t-2 border-primary">
                    <h3 className="rail-label">ТЕГИРАНО</h3>
                    <div className="flex flex-wrap gap-2">
                      {cluster.tags.map(tag => (
                        <span key={tag} className="text-[10px] font-bold uppercase text-muted">#{tag}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Related */}
                {cluster.related && cluster.related.length > 0 && (
                    <div className="rail-widget border-t-2 border-primary">
                        <h3 className="rail-label flex items-center gap-2"><Link2 size={14}/> ПОВРЗАНИ ТЕМИ</h3>
                        <div className="space-y-6">
                            {cluster.related.map((rel) => (
                                <button
                                    key={rel.cluster_id}
                                    onClick={() => navigate(`/cluster/${rel.cluster_id}`)}
                                    className="group block text-left w-full border-none bg-transparent p-0 cursor-pointer"
                                >
                                    <p className="font-serif font-bold text-sm text-primary group-hover:text-accent transition-colors leading-snug mb-2">
                                        {rel.title}
                                    </p>
                                    <div className="flex flex-wrap gap-1">
                                        {(rel.tags || []).slice(0, 3).map((tag: string) => (
                                            <span key={tag} className="text-[9px] font-bold uppercase text-muted">#{tag}</span>
                                        ))}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </aside>
        </div>
      </div>
    </div>
  );
};
