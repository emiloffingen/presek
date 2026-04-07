import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Users, TrendingUp, Newspaper, Loader2, Sparkles } from 'lucide-react';
import { apiClient } from '../api/client';
import { Header } from '../components/Header';
import { ClusterCard } from '../components/ClusterCard';

export const EntityPage: React.FC = () => {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<any>(null);
  const [clusters, setClusters] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!name) return;
    
    setLoading(true);
    // 1. Fetch entity profile
    fetch(`/api/intelligence/entity/${encodeURIComponent(name)}`)
      .then(r => r.json())
      .then(data => setProfile(data))
      .catch(() => setError("Грешка при вчитување на профилот"));

    // 2. Fetch clusters for this entity
    apiClient.getNews({ entity: name, page_size: 12 })
      .then(res => setClusters(res.clusters))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [name]);

  if (loading && !profile) {
    return (
      <div className="min-h-screen bg-primary">
        <Header />
        <div className="page-container py-20 flex flex-col items-center">
          <Loader2 className="animate-spin text-accent mb-4" size={32} />
          <p className="text-muted uppercase text-xs font-black tracking-widest">Анализираме податоци...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        <header className="mb-12 border-b-2 border-primary pb-8">
            <button 
              onClick={() => navigate(-1)}
              className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted hover:text-accent mb-6"
            >
              <ArrowLeft size={14} /> Назад
            </button>
            
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5 mb-4 inline-block">ПРОФИЛ НА ЕНТИТЕТ</span>
                <h1 className="font-serif text-4xl md:text-6xl font-bold leading-tight text-primary">
                    {name}
                </h1>
                <p className="text-muted font-bold uppercase text-xs mt-2 flex items-center gap-2">
                  <Users size={14} /> {profile?.profile?.type || 'Ентитет'}
                </p>
              </div>

              <div className="flex gap-8 border-l border-color pl-8">
                <div>
                  <p className="text-[10px] font-black text-muted uppercase mb-1">Споменувања</p>
                  <p className="text-2xl font-serif font-bold text-primary">{profile?.profile?.total_mentions || 0}</p>
                </div>
                <div>
                  <p className="text-[10px] font-black text-muted uppercase mb-1">Сентимент</p>
                  <div className="flex items-center gap-2">
                    <p className={`text-2xl font-serif font-bold ${profile?.profile?.sentiment_score > 0.1 ? 'text-emerald-600' : profile?.profile?.sentiment_score < -0.1 ? 'text-rose-600' : 'text-primary'}`}>
                      {(profile?.profile?.sentiment_score * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
              </div>
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
          <div className="lg:col-span-8">
            <h2 className="rail-label mb-8 flex items-center gap-2"><Newspaper size={16}/> ПОВРЗАНИ ВЕСТИ</h2>
            
            {clusters.length > 0 ? (
              <div className="news-feed-grid">
                {clusters.map(cluster => (
                  <ClusterCard key={cluster.cluster_id} cluster={cluster} />
                ))}
              </div>
            ) : (
              <div className="bg-secondary p-12 text-center border border-color italic text-muted">
                Нема неодамнешни вести за овој субјект.
              </div>
            )}
          </div>

          <aside className="lg:col-span-4 space-y-12">
            {profile?.related && profile.related.length > 0 && (
              <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label flex items-center gap-2"><TrendingUp size={14}/> ПОВРЗАНИ СУБЈЕКТИ</h3>
                <div className="flex flex-wrap gap-2 mt-6">
                  {profile.related.map((rel: any) => (
                    <button 
                      key={rel.related_entity}
                      onClick={() => navigate(`/entity/${encodeURIComponent(rel.related_entity)}`)}
                      className="bg-secondary border border-color px-3 py-1.5 text-xs font-bold text-primary hover:border-accent hover:text-accent transition-colors"
                    >
                      {rel.related_entity}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label flex items-center gap-2"><Sparkles size={14}/> ПРЕСЕК ИНСАЈТ</h3>
                <p className="text-[11px] leading-relaxed text-muted italic">
                  Автоматски генериран профил базиран на анализа на стотици вести во изминатиот период. Системот ги поврзува споменувањата и го мери медиумскиот третман.
                </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};
