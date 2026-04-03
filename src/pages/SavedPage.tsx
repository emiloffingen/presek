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
    <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
      <Header />
      <main className="page-container py-6">
        <div className="flex items-center gap-3 mb-6">
          <Bookmark size={20} className="text-brand-500" />
          <h1 className="text-xl font-bold text-ink dark:text-slate-100">
            Зачувани вести
          </h1>
          <span className="badge bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300">
            {savedCount}
          </span>
        </div>

        {savedCount === 0 ? (
          <div className="card p-12 text-center">
            <Bookmark size={32} className="mx-auto mb-3 text-ink-faint dark:text-slate-600" />
            <p className="font-semibold text-ink dark:text-slate-200 mb-1">Нема зачувани вести</p>
            <p className="text-sm text-ink-muted dark:text-slate-500 mb-4">
              Притиснете го иконата за зачувување на некоја вест за да ја додадете овде.
            </p>
            <button onClick={() => navigate('/')} className="btn-outline text-sm">
              Кон насловната
            </button>
          </div>
        ) : savedClusters.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {savedClusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c} variant="featured" />
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
