import React from 'react';
import { Activity, Zap, Scale, Heart } from 'lucide-react';

interface SentimentData {
  sentiment?: {
    score: number;
    tone?: string;
    label?: string;
  };
  tone_analysis?: {
    sensationalism: number;
    objectivity: number;
    emotional_charge: number;
  };
}

interface MediaPulseRadarProps {
  data: SentimentData;
}

const MediaPulseRadar: React.FC<MediaPulseRadarProps> = ({ data }) => {
  if (!data || (!data.sentiment && !data.tone_analysis)) return null;

  const rawSentiment = data.sentiment || { score: 0 };
  const sentiment = {
    score: typeof rawSentiment.score === 'number' ? rawSentiment.score : 0,
    label: rawSentiment.tone || rawSentiment.label || 'неутрален',
  };
  const tone = data.tone_analysis || { sensationalism: 0, objectivity: 0.5, emotional_charge: 0 };

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return 'text-emerald-600';
    if (score < -0.3) return 'text-amber-600';
    return 'text-blue-600';
  };

  return (
    <div className="media-pulse-radar py-6 bg-surface-soft/30 rounded-xl p-6 border border-border">
      <div className="flex items-center gap-2 mb-6">
        <Activity size={18} className="text-nyt-accent" />
        <h2 className="nyt-section-label text-nyt-accent tracking-[0.2em] mb-0">МЕДИУМСКИ ПУЛС</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="space-y-4">
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-1">Генерален тон</p>
            <div className="flex items-end gap-2">
              <span className={`text-2xl font-black uppercase tracking-tight ${getSentimentColor(sentiment.score)}`}>
                {sentiment.label}
              </span>
            </div>
          </div>
          
          <div className="relative h-2 w-full bg-border rounded-full overflow-hidden">
            <div 
              className={`absolute top-0 bottom-0 transition-all duration-1000 ${sentiment.score >= 0 ? 'bg-emerald-500' : 'bg-amber-500'}`}
              style={{ 
                left: '50%', 
                width: `${Math.abs(sentiment.score * 50)}%`,
                transform: sentiment.score < 0 ? 'translateX(-100%)' : 'none'
              }}
            />
            <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-background z-10" />
          </div>
          <div className="flex justify-between text-[9px] font-black uppercase tracking-widest text-muted-foreground">
            <span>Критичен</span>
            <span>Неутрален</span>
            <span>Позитивен</span>
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">Анализа на наративот</p>
          
          <div className="space-y-3">
            {/* Sensationalism */}
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[11px] font-bold">
                <span className="flex items-center gap-1.5"><Zap size={12} className="text-amber-500" /> Сензационализам</span>
                <span>{Math.round(tone.sensationalism * 100)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                <div className="h-full bg-amber-500 transition-all duration-1000" style={{ width: `${tone.sensationalism * 100}%` }} />
              </div>
            </div>

            {/* Objectivity */}
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[11px] font-bold">
                <span className="flex items-center gap-1.5"><Scale size={12} className="text-blue-500" /> Објективност</span>
                <span>{Math.round(tone.objectivity * 100)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 transition-all duration-1000" style={{ width: `${tone.objectivity * 100}%` }} />
              </div>
            </div>

            {/* Emotional Charge */}
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[11px] font-bold">
                <span className="flex items-center gap-1.5"><Heart size={12} className="text-rose-500" /> Емотивен набој</span>
                <span>{Math.round(tone.emotional_charge * 100)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                <div className="h-full bg-rose-500 transition-all duration-1000" style={{ width: `${tone.emotional_charge * 100}%` }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MediaPulseRadar;
