import React, { useEffect, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { fetchBriefing, BriefingData } from '@/api/client';

export const Briefing: React.FC = () => {
  const [data, setData] = useState<BriefingData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const synth = window.speechSynthesis;

  useEffect(() => {
    const load = async () => {
      try {
        const d = await fetchBriefing();
        setData(d);
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    };
    load();
    return () => synth?.cancel();
  }, [synth]);

  const toggleAudio = () => {
    if (!synth) return;
    if (isPlaying) {
      synth.cancel();
      setIsPlaying(false);
    } else if (data?.content) {
      const cleanText = data.content.replace(/\*\*/g, '').replace(/[\*•-]/g, '').trim();
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = 'mk-MK';
      utterance.onend = () => setIsPlaying(false);
      synth.speak(utterance);
      setIsPlaying(true);
    }
  };

  if (isLoading) {
    return (
      <div className="article-wrap fade-in" style={{ paddingTop: 'var(--space-xl)' }}>
        <header className="article-header">
           <div className="skeleton-box" style={{ height: '20px', width: '150px' }}></div>
           <div className="skeleton-box" style={{ height: '40px', width: '300px', marginTop: '1rem' }}></div>
        </header>
        <div className="reading-column">
          <div className="skeleton-box" style={{ height: '20px', width: '100%', marginBottom: '15px' }}></div>
          <div className="skeleton-box" style={{ height: '20px', width: '95%', marginBottom: '15px' }}></div>
          <div className="skeleton-box" style={{ height: '20px', width: '98%', marginBottom: '15px' }}></div>
        </div>
      </div>
    );
  }

  if (data?.error) {
    return <div className="error-state">{data.error}</div>;
  }

  const formattedDate = data?.date ? new Date(data.date).toLocaleDateString('mk-MK', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  }) : '';

  return (
    <div className="article-wrap fade-in" style={{ paddingTop: 'var(--space-xl)' }}>
      <header className="article-header">
        <span className="rail-label">{formattedDate}</span>
        <h1 className="nyt-title" style={{ marginTop: 'var(--space-sm)', marginBottom: 'var(--space-xl)' }}>
          Дневен Брифинг
        </h1>
        <div className="article-meta-block">
          <div className="meta-info-left">
            <span>ПРЕСЕК УТРО</span>
            <span>Најважните настани резимирани за вас</span>
          </div>
          <div className="meta-info-right" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button className="icon-btn" onClick={toggleAudio} title="Слушни го брифингот" style={{ color: isPlaying ? 'var(--primary)' : 'inherit' }}>
              {isPlaying ? <VolumeX size={20} /> : <Volume2 size={20} />}
            </button>
          </div>
        </div>
      </header>

      <div className="reading-column">
        <div className="briefing-content">
          {data?.content.split('\n\n').filter(p => p.trim()).map((para, i) => {
            if (para.startsWith('**') && para.endsWith('**') && !para.includes('\n')) {
              return (
                <h2 key={i} className="rail-label section-header" style={{ marginTop: 'var(--space-xl)' }}>
                  {para.replace(/\*\*/g, '')}
                </h2>
              );
            }
            return (
              <p key={i} dangerouslySetInnerHTML={{
                __html: para
                  .replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--text-primary);">$1</strong>')
                  .replace(/^[\*•-]\s+(.*)/gm, '<span style="color: var(--primary); margin-right: 8px;">•</span> $1')
                  .replace(/\n/g, '<br />')
              }} />
            );
          })}
        </div>
        <div className="briefing-footer">
          Овој брифинг е генериран од Пресек AI врз основа на медиумското покривање во последните 24 часа.
        </div>
      </div>
    </div>
  );
};
