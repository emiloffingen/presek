import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Bookmark } from 'lucide-react';
import { Header } from '../components/Header';
import { ClusterCard } from '../components/ClusterCard';
import { useSavedStore } from '../store/useNewsStore';
import { useNewsStore } from '../store/useNewsStore';

export const SavedPage: React.FC = () => {
  const navigate = useNavigate();
  const { savedIds } = useSavedStore();
  const { clusters } = useNewsStore();

  // Match saved IDs against any loaded clusters; show what we have
  const savedClusters = clusters.filter((c) => savedIds.has(c.cluster_id));
  const savedCount = savedIds.size;

  return (
    <div className="min-h-screen bg-primary">
      <Header />
      <main className="site-layout py-8">
        <div className="flex items-center gap-3 mb-8 border-b-2 border-primary pb-6">
          <Bookmark size={24} className="text-accent" />
          <h1 className="font-serif text-3xl font-bold text-primary">
            Зачувани вести
          </h1>
          <span className="text-xs font-black uppercase text-muted ml-auto">
            {savedCount} вести
          </span>
        </div>

        {savedCount === 0 ? (
          <div className="bg-secondary p-12 text-center border-t-2 border-accent">
            <Bookmark size={32} className="mx-auto mb-3 text-muted" />
            <p className="font-bold text-primary mb-1">Нема зачувани вести</p>
            <p className="text-sm text-muted mb-6 italic">
              Притиснете го иконата за зачувување на некоја вест за да ја додадете овде.
            </p>
            <button onClick={() => navigate('/')} className="text-[10px] font-black uppercase text-primary hover:underline">
              Кон насловната
            </button>
          </div>
        ) : savedClusters.length > 0 ? (
          <div className="news-feed-grid">
            {savedClusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c} />
            ))}
          </div>
        ) : (
          <div className="card p-8 text-center">
            <p className="text-sm text-ink-muted dark:text-slate-500">
              Имате {savedCount} зачувани вести, но тие не се вчитани во моментов.
            </p>
            <button onClick={() => navigate('/')} className="btn-outline text-sm mt-4">
              Вчитај ги
            </button>
          </div>
        )}
      </main>
    </div>
  );
};
