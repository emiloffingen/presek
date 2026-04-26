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
  const sensationalism = Math.min(100, Math.max(0, (tone_analysis?.sensationalism || 0) * 100));
  const objectivity = Math.min(100, Math.max(0, (tone_analysis?.objectivity || 0) * 100));
  const emotionalCharge = Math.min(100, Math.max(0, (tone_analysis?.emotional_charge || 0) * 100));
  
  // Scale factor for animation
  const scale = isMounted ? 1 : 0.01;

  // Center of the SVG
  const cx = 100;
  const cy = 100;
  const radius = 70;

  // Calculate coordinates for the 3 points
  // 0 degrees: Objectivity (Top)
  const x1 = cx + radius * (objectivity / 100) * Math.sin(0) * scale;
  const y1 = cy - (radius * (objectivity / 100) * Math.cos(0) * scale);

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
    <div className="media-pulse-card bg-zinc-50/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 p-6 md:p-8 rounded-xl shadow-sm">
      <div className="flex flex-col lg:flex-row gap-10 items-center">
        {/* Radar Visualization */}
        <div className="relative w-56 h-56 flex-shrink-0">
          <svg viewBox="0 0 200 200" className="w-full h-full overflow-visible drop-shadow-sm">
            {/* Background circles */}
            {[1, 0.75, 0.5, 0.25].map((lvl) => (
                <circle 
                    key={lvl}
                    cx="100" cy="100" r={radius * lvl} 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="0.5" 
                    className="text-zinc-300 dark:text-zinc-700" 
                    strokeDasharray={lvl === 1 ? "none" : "2 2"} 
                />
            ))}
            
            {/* Axis lines */}
            <line x1="100" y1={cy - radius} x2="100" y2="100" stroke="currentColor" strokeWidth="1" className="text-zinc-300 dark:text-zinc-700" />
            <line x1="100" y1="100" x2={cx + radius * Math.sin(120 * Math.PI / 180)} y2={cy - radius * Math.cos(120 * Math.PI / 180)} stroke="currentColor" strokeWidth="1" className="text-zinc-300 dark:text-zinc-700" />
            <line x1="100" y1="100" x2={cx + radius * Math.sin(240 * Math.PI / 180)} y2={cy - radius * Math.cos(240 * Math.PI / 180)} stroke="currentColor" strokeWidth="1" className="text-zinc-300 dark:text-zinc-700" />

            {/* Labels */}
            <text x="100" y={cy - radius - 12} textAnchor="middle" className="text-[10px] font-black fill-zinc-500 dark:fill-zinc-400 uppercase tracking-[0.1em]">Објективност</text>
            <text x={cx + radius * Math.sin(120 * Math.PI / 180) + 15} y={cy - radius * Math.cos(120 * Math.PI / 180) + 15} textAnchor="middle" className="text-[10px] font-black fill-zinc-500 dark:fill-zinc-400 uppercase tracking-[0.1em]">Сензационализам</text>
            <text x={cx + radius * Math.sin(240 * Math.PI / 180) - 15} y={cy - radius * Math.cos(240 * Math.PI / 180) + 15} textAnchor="middle" className="text-[10px] font-black fill-zinc-500 dark:fill-zinc-400 uppercase tracking-[0.1em]">Емоции</text>

            {/* Data shape */}
            <polygon 
              points={points} 
              fill="var(--nyt-accent)"
              fillOpacity="0.15"
              stroke="var(--nyt-accent)" 
              strokeWidth="2.5"
              strokeLinejoin="round"
              className="transition-all duration-[1200ms] cubic-bezier(0.34, 1.56, 0.64, 1)"
            />
            
            {/* Points */}
            <circle cx={x1} cy={y1} r="5" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.34, 1.56, 0.64, 1) stroke-[3px] stroke-white dark:stroke-zinc-900" />
            <circle cx={x2} cy={y2} r="5" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.34, 1.56, 0.64, 1) stroke-[3px] stroke-white dark:stroke-zinc-900" />
            <circle cx={x3} cy={y3} r="5" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.34, 1.56, 0.64, 1) stroke-[3px] stroke-white dark:stroke-zinc-900" />
          </svg>
        </div>

        {/* Text Metrics */}
        <div className="flex-1 w-full space-y-6">
          <div>
            <span className="inline-block bg-zinc-200 dark:bg-zinc-800 px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest text-zinc-600 dark:text-zinc-400 mb-2">Медиумски Пулс</span>
            <p className="text-3xl font-serif font-black leading-tight text-zinc-900 dark:text-zinc-100">
              Тон: <span className={getSentimentColor(sentiment.score)}>{sentiment.tone}</span>
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 lg:gap-8 pt-6 border-t border-zinc-200 dark:border-zinc-800">
            <div className="space-y-2">
              <span className="text-[10px] font-black uppercase text-zinc-500 dark:text-zinc-400 block tracking-wider">Објективност</span>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-black tabular-nums">{objectivity.toFixed(0)}%</span>
                <div className="h-1.5 flex-1 mb-2 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-zinc-900 dark:bg-zinc-100 transition-all duration-1000 delay-300" style={{ width: isMounted ? `${objectivity}%` : '0%' }}></div>
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <span className="text-[10px] font-black uppercase text-zinc-500 dark:text-zinc-400 block tracking-wider">Сензационализам</span>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-black tabular-nums">{sensationalism.toFixed(0)}%</span>
                <div className="h-1.5 flex-1 mb-2 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-red-600 transition-all duration-1000 delay-500" style={{ width: isMounted ? `${sensationalism}%` : '0%' }}></div>
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <span className="text-[10px] font-black uppercase text-zinc-500 dark:text-zinc-400 block tracking-wider">Емоционалност</span>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-black tabular-nums">{emotionalCharge.toFixed(0)}%</span>
                <div className="h-1.5 flex-1 mb-2 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-500 transition-all duration-1000 delay-700" style={{ width: isMounted ? `${emotionalCharge}%` : '0%' }}></div>
                </div>
              </div>
            </div>
          </div>

          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 font-medium leading-relaxed italic border-l-2 border-zinc-200 dark:border-zinc-800 pl-4 py-1">
            * Оваа анализа е генерирана автоматски преку споредба на јазичните форми и структурата на известување кај сите вклучени медиуми.
          </p>
        </div>
      </div>
    </div>
  );
};
