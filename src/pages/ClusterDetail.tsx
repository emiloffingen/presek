import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { 
  Volume2, VolumeX, Share2, Type, 
  ChevronRight, MessageCircle, X, Send 
} from 'lucide-react';
import { fetchClusterDetail, ClusterDetailData, askAI } from '@/api/client';

export const ClusterDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ClusterDetailData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [fontSize, setFontSize] = useState(1); // 1 = normal, 1.2 = large
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatQuery, setChatQuery] = useState('');
  const [chatResponse, setChatResponse] = useState<string | null>(null);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const synth = window.speechSynthesis;

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setIsLoading(true);
      try {
        const d = await fetchClusterDetail(id);
        setData(d);
        window.scrollTo(0, 0);
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    };
    load();
    return () => synth?.cancel();
  }, [id, synth]);

  const toggleAudio = () => {
    if (!synth || !data) return;
    if (isPlaying) {
      synth.cancel();
      setIsPlaying(false);
    } else {
      const textToRead = data.synthesis || data.articles[0].title;
      const utterance = new SpeechSynthesisUtterance(textToRead);
      utterance.lang = 'mk-MK';
      utterance.onend = () => setIsPlaying(false);
      synth.speak(utterance);
      setIsPlaying(true);
    }
  };

  const handleAsk = async (predefined?: string) => {
    const query = predefined || chatQuery.trim();
    if (!query || !id) return;
    
    setChatQuery(query);
    setIsChatOpen(true);
    setIsChatLoading(true);
    setChatResponse(null);
    
    try {
      const resp = await askAI(id, query);
      setChatResponse(resp);
    } catch (e) {
      setChatResponse('Грешка при поврзување со AI.');
    } finally {
      setIsChatLoading(false);
    }
  };

  const share = () => {
    if (navigator.share && data) {
      navigator.share({
        title: data.articles[0].title,
        url: window.location.href
      });
    } else {
      alert('Линк копиран во таблата!');
      navigator.clipboard.writeText(window.location.href);
    }
  };

  if (isLoading || !data) {
    return (
      <div className="article-wrap fade-in" style={{ paddingTop: 'var(--space-xl)' }}>
        <header className="article-header">
           <div className="skeleton-box" style={{ height: '40px', width: '80%', marginBottom: '1rem' }}></div>
           <div className="skeleton-box" style={{ height: '20px', width: '60%' }}></div>
        </header>
        <div className="reading-column">
          <div className="skeleton-box" style={{ height: '300px', width: '100%', marginBottom: '2rem' }}></div>
          <div className="skeleton-box" style={{ height: '20px', width: '100%', marginBottom: '1rem' }}></div>
          <div className="skeleton-box" style={{ height: '20px', width: '95%', marginBottom: '1rem' }}></div>
        </div>
      </div>
    );
  }

  const main = data.articles[0];
  const heroImage = data.articles.find(a => a.image_url)?.image_url;

  return (
    <article className="article-wrap fade-in" style={{ paddingTop: 'var(--space-xl)' }}>
      <header className="article-header">
        <h1 className="nyt-title" style={{ fontSize: `${2.5 * fontSize}rem` }}>{main.title}</h1>
        <p className="cluster-excerpt" style={{ fontSize: `${1.2 * fontSize}rem`, color: 'var(--text-secondary)', marginBottom: 'var(--space-lg)' }}>
          {main.description || 'Преглед на најважните вести од повеќе извори.'}
        </p>

        <div className="article-meta-block">
          <div className="meta-info-left">
            <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>Пресек Анализа</span>
            <span>{new Date(main.created_at).toLocaleDateString('mk-MK', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
            <span>{data.articles.length} Извори</span>
            {data.total_reading_time > 0 && <span>{data.total_reading_time} мин читање</span>}
          </div>
          <div className="meta-info-right" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button className="icon-btn" onClick={toggleAudio} title="Слушни го текстот">
              {isPlaying ? <VolumeX size={18} /> : <Volume2 size={18} />}
            </button>
            <button className="icon-btn" onClick={share} title="Сподели">
              <Share2 size={18} />
            </button>
            <div className="reading-toolkit" style={{ margin: 0, background: 'none', border: 'none' }}>
              <div className="tk-btn" onClick={() => setFontSize(Math.max(0.8, fontSize - 0.1))}>A-</div>
              <div className="tk-btn inc" onClick={() => setFontSize(Math.min(1.4, fontSize + 0.1))}>A+</div>
            </div>
          </div>
        </div>
      </header>

      {heroImage && (
        <div className="cluster-hero fade-in">
          <img 
            src={heroImage.startsWith('/') ? heroImage : `/proxy?url=${encodeURIComponent(heroImage)}`} 
            className="hero-img" 
            alt={main.title} 
            loading="eager" 
          />
        </div>
      )}

      <div className="reading-column" style={{ fontSize: `${1.1 * fontSize}rem` }}>
        {data.synthesis && (
          <section className="cluster-summary fade-in">
            {data.synthesis.split('\n\n').filter(p => p.trim()).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </section>
        )}

        {data.perspectives && data.perspectives.length > 0 && (
          <section className="perspectives-list fade-in" style={{ marginBottom: 'var(--space-2xl)' }}>
            <h2 className="rail-label">Анализа на перспективи</h2>
            {data.perspectives.map((p, i) => (
              <div key={i} className="perspective-quote">
                <div className="perspective-text">{p}</div>
              </div>
            ))}
          </section>
        )}

        <section className="ai-ask-section fade-in" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-xl)' }}>
          <div className="ai-ask-row" style={{ maxWidth: '100%' }}>
            <input 
              type="text" 
              className="ai-ask-input" 
              placeholder="Имате прашање за овој настан?"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAsk()}
            />
            <button className="page-btn" onClick={() => handleAsk()}>Прашај</button>
          </div>
          <div className="suggested-questions">
            <button className="sq-btn" onClick={() => handleAsk('Кои се главните спротивставени ставови?')}>Главни ставови?</button>
            <button className="sq-btn" onClick={() => handleAsk('Што се очекува да се случи следно?')}>Што следно?</button>
            <button className="sq-btn" onClick={() => handleAsk('Направи кратко резиме во 3 точки.')}>Резиме во 3 точки</button>
          </div>
        </section>

        <div style={{ marginTop: 'var(--space-2xl)' }}>
          <h2 className="rail-label">Извори на веста</h2>
          <div className="sources-grid">
            {data.articles.map((art, i) => (
              <a key={i} href={art.link} target="_blank" rel="noopener noreferrer" className="source-card fade-in" style={{ borderColor: 'var(--border-strong)' }}>
                <div className="source-content">
                  <div style={{ marginBottom: '8px' }}>
                    <span className="category" style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-primary)' }}>{art.source}</span>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginLeft: '8px', fontFamily: 'var(--font-mono)' }}>
                      {new Date(art.created_at).toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <h3 className="source-title" style={{ fontSize: '1.1rem', marginBottom: '8px', fontFamily: 'var(--font-heading)' }}>{art.title}</h3>
                </div>
                {art.image_url && (
                  <div className="source-thumb-wrap" style={{ width: '100px', aspectRatio: '3/2', marginBottom: 0 }}>
                    <img src={art.image_url.startsWith('/') ? art.image_url : `/proxy?url=${encodeURIComponent(art.image_url)}`} className="source-thumb" loading="lazy" alt={art.source} />
                  </div>
                )}
              </a>
            ))}
          </div>
        </div>

        {data.related && data.related.length > 0 && (
          <div style={{ marginTop: 'var(--space-2xl)', borderTop: '2px solid var(--text-primary)', paddingTop: 'var(--space-xl)' }}>
            <h2 className="rail-label">Поврзани Вести</h2>
            <div className="related-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--space-lg)' }}>
              {data.related.map((rel, i) => (
                <Link key={i} to={`/cluster/${rel.cluster_id}`} className="related-item fade-in" style={{ textDecoration: 'none', color: 'inherit' }}>
                   {rel.image_url && (
                     <img 
                      src={rel.image_url.startsWith('/') ? rel.image_url : `/proxy?url=${encodeURIComponent(rel.image_url)}`} 
                      style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', marginBottom: '8px' }} 
                      alt={rel.title}
                    />
                   )}
                   <h4 style={{ fontFamily: 'var(--font-heading)', fontSize: '1rem', lineHeight: 1.3 }}>{rel.title}</h4>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={`ai-sheet ${isChatOpen ? 'active' : ''}`} id="aiSheet">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-lg)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.15rem', letterSpacing: 'var(--tracking-tight)' }}>Пресек Дијалог</h2>
          <button className="icon-btn" onClick={() => setIsChatOpen(false)} aria-label="Затвори">
            <X size={18} />
          </button>
        </div>
        <div className="ai-content" id="aiResponse">
          {isChatLoading ? (
            <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Размислувам...</p>
          ) : (
            chatResponse ? (
              <div dangerouslySetInnerHTML={{ 
                __html: `<p>${chatResponse.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>')}</p>` 
              }} />
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>Нема прашање.</p>
            )
          )}
        </div>
      </div>
    </article>
  );
};
