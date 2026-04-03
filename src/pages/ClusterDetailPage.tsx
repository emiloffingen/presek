import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Flame, Sparkles, Newspaper, Link2,
  MessageCircle, Loader2, Clock, Tag, Send,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ClusterDetail } from '../types';
import { ArticleCard } from '../components/ArticleCard';
import { Header } from '../components/Header';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Тукушто';
  if (mins < 60) return `${mins} мин`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} часа`;
  return `${Math.floor(hrs / 24)} дена`;
}

export const ClusterDetailPage: React.FC = () => {
  const { clusterId } = useParams<{ clusterId: string }>();
  const navigate = useNavigate();
  const [cluster, setCluster] = useState<ClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatQuery, setChatQuery] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResponse, setChatResponse] = useState<string | null>(null);

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    apiClient.getClusterDetail(clusterId)
      .then((res) => { setCluster(res.data); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Грешка'))
      .finally(() => setLoading(false));
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

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
        <Header />
        <div className="page-container py-12 flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-brand-600" />
          <p className="text-ink-muted dark:text-slate-400">Вчитување...</p>
        </div>
      </div>
    );
  }

  if (error || !cluster) {
    return (
      <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
        <Header />
        <div className="page-container py-12 text-center">
          <p className="text-brand-600 dark:text-brand-400 mb-4">{error || 'Кластерот не е пронајден'}</p>
          <button onClick={() => navigate('/')} className="btn-primary">
            <ArrowLeft size={16} />
            Назад
          </button>
        </div>
      </div>
    );
  }

  const article = cluster.articles[0];
  const imageUrl = apiClient.getImageUrl(cluster.representative_image || article?.image_url, 1200);

  return (
    <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
      <Header />

      {/* Hero image */}
      {imageUrl && (
        <div className="relative w-full overflow-hidden bg-dark-0" style={{ maxHeight: 480 }}>
          <img src={imageUrl} alt="" className="w-full object-cover" style={{ maxHeight: 480 }} />
          <div className="absolute inset-0 img-overlay" />
          <div className="absolute bottom-0 left-0 right-0 p-6 md:p-8 page-container">
            <div className="flex flex-wrap gap-2 mb-3">
              {cluster.is_breaking && (
                <span className="badge-breaking flex items-center gap-1">
                  <Flame size={12} />
                  BREAKING
                </span>
              )}
              {cluster.has_synthesis && (
                <span className="badge-synthesis flex items-center gap-1">
                  <Sparkles size={12} />
                  Синтеза
                </span>
              )}
            </div>
            <h1 className="text-2xl md:text-4xl font-bold text-white leading-tight max-w-3xl">
              {article?.title}
            </h1>
          </div>
        </div>
      )}

      <div className="page-container py-6">
        {/* Back + meta */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="btn-ghost text-sm shrink-0"
          >
            <ArrowLeft size={16} />
            Назад
          </button>
          <div className="flex flex-wrap gap-2 text-xs text-ink-muted dark:text-slate-400">
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {timeAgo(article?.created_at || '')}
            </span>
            <span className="flex items-center gap-1">
              <Newspaper size={12} />
              {cluster.articles.length} {cluster.articles.length === 1 ? 'статија' : 'статии'}
            </span>
            {cluster.total_reading_time > 0 && (
              <span>· {cluster.total_reading_time} мин читање</span>
            )}
          </div>
        </div>

        {/* If no hero image, show title here */}
        {!imageUrl && (
          <div className="mb-6">
            <div className="flex flex-wrap gap-2 mb-3">
              {cluster.is_breaking && (
                <span className="badge-breaking flex items-center gap-1">
                  <Flame size={12} />
                  BREAKING
                </span>
              )}
              {cluster.has_synthesis && (
                <span className="badge-synthesis flex items-center gap-1">
                  <Sparkles size={12} />
                  Синтеза
                </span>
              )}
            </div>
            <h1 className="text-2xl md:text-3xl font-bold text-ink dark:text-white leading-tight">
              {article?.title}
            </h1>
          </div>
        )}

        {/* Tags */}
        {cluster.tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-6">
            {cluster.tags.map((tag, i) => (
              <span key={i} className="flex items-center gap-1 badge bg-surface-2 dark:bg-dark-3 text-ink-soft dark:text-slate-400">
                <Tag size={10} />
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* AI Synthesis */}
            {cluster.has_synthesis && cluster.synthesis && (
              <div className="card p-6 border-l-4 border-amber-500">
                <div className="flex items-center gap-2 mb-4">
                  <Sparkles size={18} className="text-amber-500" />
                  <h2 className="font-bold text-lg text-ink dark:text-white">АИ Синтеза</h2>
                </div>
                <p className="article-prose text-base leading-relaxed mb-4">{cluster.synthesis}</p>

                {cluster.perspectives.length > 0 && (
                  <div className="mt-4 space-y-3">
                    <p className="section-heading">Различни перспективи</p>
                    {cluster.perspectives.map((p, i) => (
                      <div key={i} className="rounded-lg bg-surface-1 dark:bg-dark-2 border border-surface-3 dark:border-dark-3 p-4">
                        <p className="font-semibold text-sm text-ink dark:text-slate-200 mb-1">{p.angle}</p>
                        <p className="text-sm text-ink-muted dark:text-slate-400">{p.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* All articles */}
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Newspaper size={16} className="text-ink-muted dark:text-slate-400" />
                <h2 className="font-bold text-lg text-ink dark:text-white">
                  Сите извори ({cluster.articles.length})
                </h2>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {cluster.articles.map((article) => (
                  <ArticleCard
                    key={article.id}
                    article={article}
                    onClick={() => window.open(article.link, '_blank')}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Right sidebar */}
          <div className="space-y-5">
            {/* AI Chat */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <MessageCircle size={16} className="text-blue-500" />
                <h3 className="font-bold text-base text-ink dark:text-white">Прашај АИ</h3>
              </div>
              <form onSubmit={handleChat} className="space-y-3">
                <textarea
                  value={chatQuery}
                  onChange={(e) => setChatQuery(e.target.value)}
                  placeholder="Прашај нешто за овие вести..."
                  rows={3}
                  disabled={chatLoading}
                  className="input resize-none"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatQuery.trim()}
                  className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {chatLoading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                  {chatLoading ? 'Обработка...' : 'Прашај'}
                </button>
              </form>
              {chatResponse && (
                <div className="mt-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 p-4">
                  <p className="text-sm text-ink dark:text-slate-200 leading-relaxed">{chatResponse}</p>
                </div>
              )}
            </div>

            {/* Related clusters */}
            {cluster.related.length > 0 && (
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Link2 size={16} className="text-ink-muted dark:text-slate-400" />
                  <h3 className="font-bold text-base text-ink dark:text-white">Поврзани</h3>
                </div>
                <div className="space-y-3">
                  {cluster.related.map((rel) => (
                    <button
                      key={rel.cluster_id}
                      onClick={() => navigate(`/cluster/${rel.cluster_id}`)}
                      className="w-full flex items-start gap-3 text-left group"
                    >
                      {rel.image_url && (
                        <div className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-surface-3 dark:bg-dark-3">
                          <img
                            src={apiClient.getImageUrl(rel.image_url, 150)}
                            alt=""
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                          />
                        </div>
                      )}
                      <p className="text-sm font-medium text-ink dark:text-slate-200 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors line-clamp-2 leading-snug">
                        {rel.title}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
