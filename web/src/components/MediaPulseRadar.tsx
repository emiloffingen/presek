import React from 'react';

interface ToneAnalysis {
  sensationalism: number;
  objectivity: number;
  emotional_charge: number;
}

interface SentimentData {
  sentiment: {
    score: number;
    tone: string;
  };
  tone_analysis: ToneAnalysis;
}

interface Props {
  data: SentimentData;
}

export const MediaPulseRadar: React.FC<Props> = ({ data }) => {
  const { tone_analysis, sentiment } = data;
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => {
    const timer = setTimeout(() => setIsMounted(true), 50);
    return () => clearTimeout(timer);
  }, []);
  
  // Normalize values to 0-100 for the SVG
  const sensationalism = (tone_analysis?.sensationalism || 0) * 100;
  const objectivity = (tone_analysis?.objectivity || 0) * 100;
  const emotionalCharge = (tone_analysis?.emotional_charge || 0) * 100;
  
  // Scale factor for animation
  const scale = isMounted ? 1 : 0.1;

  // Center of the SVG
  const cx = 100;
  const cy = 100;
  const radius = 70;

  // Calculate coordinates for the 3 points
  // 0 degrees: Objectivity (Top)
  const x1 = cx + radius * (objectivity / 100) * Math.sin(0) * scale;
  const y1 = cy - (radius * (objectivity / 100) * Math.cos(0) * scale) + (1-scale)*cy*0.1;

  // 120 degrees: Sensationalism (Bottom Right)
  const x2 = cx + radius * (sensationalism / 100) * Math.sin((120 * Math.PI) / 180) * scale;
  const y2 = cy - radius * (sensationalism / 100) * Math.cos((120 * Math.PI) / 180) * scale;

  // 240 degrees: Emotional Charge (Bottom Left)
  const x3 = cx + radius * (emotionalCharge / 100) * Math.sin((240 * Math.PI) / 180) * scale;
  const y3 = cy - radius * (emotionalCharge / 100) * Math.cos((240 * Math.PI) / 180) * scale;

  const points = `${x1},${y1} ${x2},${y2} ${x3},${y3}`;

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return 'text-emerald-600 dark:text-emerald-400';
    if (score < -0.3) return 'text-red-600 dark:text-red-400';
    return 'text-amber-600 dark:text-amber-400';
  };

  return (
    <div className="media-pulse-card bg-card border border-border p-6 rounded-lg shadow-sm">
      <div className="flex flex-col md:flex-row gap-8 items-center">
        <div className="relative w-48 h-48 flex-shrink-0">
          <svg viewBox="0 0 200 200" className="w-full h-full overflow-visible">
            {/* Background circles */}
            <circle cx="100" cy="100" r="70" fill="none" stroke="currentColor" strokeWidth="1" className="text-border dark:text-muted-foreground/30" strokeDasharray="4 4" />
            <circle cx="100" cy="100" r="35" fill="none" stroke="currentColor" strokeWidth="1" className="text-border dark:text-muted-foreground/30" strokeDasharray="4 4" />
            
            {/* Axis lines */}
            <line x1="100" y1="30" x2="100" y2="100" stroke="currentColor" strokeWidth="1" className="text-border dark:text-muted-foreground/30" />
            <line x1="100" y1="100" x2="160.6" y2="135" stroke="currentColor" strokeWidth="1" className="text-border dark:text-muted-foreground/30" />
            <line x1="100" y1="100" x2="39.4" y2="135" stroke="currentColor" strokeWidth="1" className="text-border dark:text-muted-foreground/30" />

            {/* Labels */}
            <text x="100" y="20" textAnchor="middle" className="text-[10px] font-bold fill-muted-foreground dark:fill-foreground uppercase tracking-wider">Објективност</text>
            <text x="175" y="145" textAnchor="middle" className="text-[10px] font-bold fill-muted-foreground dark:fill-foreground uppercase tracking-wider">Сензационализам</text>
            <text x="25" y="145" textAnchor="middle" className="text-[10px] font-bold fill-muted-foreground dark:fill-foreground uppercase tracking-wider">Емоции</text>

            {/* Data shape */}
            <polygon 
              points={points} 
              fill="var(--nyt-red)"
              fillOpacity="0.2"
              stroke="var(--nyt-red)" 
              strokeWidth="2"
              className="transition-all duration-[800ms] cubic-bezier(0.34, 1.56, 0.64, 1)"
            />
            
            {/* Points */}
            <circle cx={x1} cy={y1} r="4" fill="var(--nyt-red)" className="transition-all duration-[800ms] cubic-bezier(0.34, 1.56, 0.64, 1)" />
            <circle cx={x2} cy={y2} r="4" fill="var(--nyt-red)" className="transition-all duration-[800ms] cubic-bezier(0.34, 1.56, 0.64, 1)" />
            <circle cx={x3} cy={y3} r="4" fill="var(--nyt-red)" className="transition-all duration-[800ms] cubic-bezier(0.34, 1.56, 0.64, 1)" />
          </svg>
        </div>

        <div className="flex-1 space-y-4">
          <div>
            <h3 className="nyt-section-label text-nyt-accent mb-1 tracking-widest">Медиумски Пулс</h3>
            <p className="text-2xl font-serif font-black capitalize leading-tight">
              Тон: <span className={getSentimentColor(sentiment.score)}>{sentiment.tone}</span>
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 border-t border-border pt-4">
            <div className="space-y-1">
              <span className="text-[10px] font-black uppercase text-muted-foreground block">Објективност</span>
              <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div className="h-full bg-foreground" style={{ width: `${objectivity}%` }}></div>
              </div>
              <span className="text-xs font-bold">{objectivity}%</span>
            </div>
            <div className="space-y-1">
              <span className="text-[10px] font-black uppercase text-muted-foreground block">Сензационализам</span>
              <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div className="h-full bg-nyt-red" style={{ width: `${sensationalism}%` }}></div>
              </div>
              <span className="text-xs font-bold">{sensationalism}%</span>
            </div>
            <div className="space-y-1">
              <span className="text-[10px] font-black uppercase text-muted-foreground block">Емоционалност</span>
              <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div className="h-full bg-amber-500" style={{ width: `${emotionalCharge}%` }}></div>
              </div>
              <span className="text-xs font-bold">{emotionalCharge}%</span>
            </div>
          </div>

          <p className="text-xs text-muted-foreground italic leading-relaxed">
            * Оваа анализа е генерирана автоматски преку споредба на јазичните форми и структурата на известување кај сите вклучени медиуми.
          </p>
        </div>
      </div>
    </div>
  );
};
