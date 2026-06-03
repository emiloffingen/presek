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
  lang?: 'sr' | 'mk';
}

export const MediaPulseRadar: React.FC<Props> = ({ data, lang = 'sr' }) => {
  const { tone_analysis, sentiment } = data;
  const [isMounted, setIsMounted] = React.useState(false);
  const [activeTooltip, setActiveTooltip] = React.useState<{x: number, y: number, label: string, value: string} | null>(null);

  React.useEffect(() => {
    const timer = setTimeout(() => setIsMounted(true), 50);
    return () => clearTimeout(timer);
  }, []);

  const labels = {
    objectivity: lang === 'mk' ? 'Објективност' : 'Objektivnost',
    sensationalism: lang === 'mk' ? 'Сензационализам' : 'Senzacionalizam',
    emotions: lang === 'mk' ? 'Емоции' : 'Emocije',
    mediaPulse: lang === 'mk' ? 'Медиумски пулс' : 'Medijski puls',
    tone: lang === 'mk' ? 'Тон' : 'Ton',
    emotionality: lang === 'mk' ? 'Емоционалност' : 'Emocionalnost',
    note: lang === 'mk'
      ? '* оваа анализа е генерирана автоматски преку споредба на јазичните форми и структурата на известување кај сите вклучени медиуми.'
      : '* ova analiza je generisana automatski kroz poređenje jezičkih formi i strukture izveštavanja kod svih uključenih medija.',
  };

  // Normalize values to 0-100 for the SVG. The parent only renders this component
  // when all three metrics are present, so 0 remains a valid real value here.
  const sensationalism = Math.min(100, Math.max(0, tone_analysis.sensationalism * 100));
  const objectivity = Math.min(100, Math.max(0, tone_analysis.objectivity * 100));
  const emotionalCharge = Math.min(100, Math.max(0, tone_analysis.emotional_charge * 100));

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
    <div className="media-pulse-card p-5 md:p-6 rounded-xl overflow-hidden relative">
      <style>{`
        .media-pulse-card {
          background: linear-gradient(135deg, rgba(254, 252, 246, 0.75) 0%, rgba(246, 240, 228, 0.7) 100%);
          backdrop-filter: var(--glass-blur);
          -webkit-backdrop-filter: var(--glass-blur);
          border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
          box-shadow: 0 8px 32px 0 color-mix(in srgb, var(--background) 30%, rgba(0, 0, 0, 0.08)),
                      inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 6%, transparent);
          transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .dark .media-pulse-card {
          background: linear-gradient(135deg, rgba(22, 26, 41, 0.7) 0%, rgba(15, 18, 29, 0.65) 100%);
          border-color: color-mix(in srgb, var(--border) 80%, transparent);
          box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.3),
                      inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 4%, transparent);
        }
        
        .media-pulse-card:hover {
          border-color: color-mix(in srgb, var(--nyt-accent) 35%, var(--border));
          box-shadow: 0 16px 48px 0 color-mix(in srgb, var(--background) 50%, rgba(0, 0, 0, 0.18)),
                      inset 0 1px 0px 0px color-mix(in srgb, var(--foreground) 10%, transparent),
                      0 0 30px -4px color-mix(in srgb, var(--nyt-accent) 6%, transparent);
          transform: translateY(-2px);
        }
        
        .radar-sweep-line {
          transform-origin: 100px 100px;
          animation: radar-sweep-rotate 5s linear infinite;
        }
        
        @keyframes radar-sweep-rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        .radar-polygon {
          filter: drop-shadow(0 0 5px color-mix(in srgb, var(--nyt-accent) 30%, transparent));
          transition: all 1.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .media-pulse-card:hover .radar-polygon {
          filter: drop-shadow(0 0 8px color-mix(in srgb, var(--nyt-accent) 50%, transparent));
          fill-opacity: 0.25;
        }
        
        .pulse-stat-row {
          transition: all 0.3s var(--ease-editorial);
          padding: 0.35rem 0.5rem;
          margin: 0 -0.5rem;
          border-radius: var(--radius-lg, 0px);
        }
        
        .pulse-stat-row:hover {
          background: color-mix(in srgb, var(--foreground) 3%, transparent);
          transform: translateX(4px);
        }
      `}</style>
      <div className="flex flex-col md:flex-row gap-6 md:gap-8 items-center">
        {/* Radar Visualization */}
        <div className="relative w-56 h-56 md:w-60 md:h-60 flex-shrink-0 mx-auto">
          <svg viewBox="0 0 200 200" className="w-full h-full overflow-visible drop-shadow-md relative z-10">
            {/* Background circles */}
            {[1, 0.75, 0.5, 0.25].map((lvl) => (
                <circle
                    key={lvl}
                    cx="100" cy="100" r={radius * lvl}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="0.75"
                    className="text-border"
                    strokeDasharray={lvl === 1 ? "none" : "3 3"}
                />
            ))}

            {/* Axis lines */}
            <line x1="100" y1={cy - radius} x2="100" y2="100" stroke="currentColor" strokeWidth="1.5" className="text-border" />
            <line x1="100" y1="100" x2={cx + radius * Math.sin(120 * Math.PI / 180)} y2={cy - radius * Math.cos(120 * Math.PI / 180)} stroke="currentColor" strokeWidth="1.5" className="text-border" />
            <line x1="100" y1="100" x2={cx + radius * Math.sin(240 * Math.PI / 180)} y2={cy - radius * Math.cos(240 * Math.PI / 180)} stroke="currentColor" strokeWidth="1.5" className="text-border" />

            {/* Labels */}
            <text x="100" y={cy - radius - 15} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">{labels.objectivity}</text>
            <text x={cx + radius * Math.sin(120 * Math.PI / 180) + 18} y={cy - radius * Math.cos(120 * Math.PI / 180) + 18} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">{labels.sensationalism}</text>
            <text x={cx + radius * Math.sin(240 * Math.PI / 180) - 18} y={cy - radius * Math.cos(240 * Math.PI / 180) + 18} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">{labels.emotions}</text>

            {/* Radar Scanning Line */}
            <line x1="100" y1="100" x2="100" y2={100 - radius} stroke="var(--nyt-accent)" strokeWidth="1.5" strokeOpacity="0.25" className="radar-sweep-line pointer-events-none" />

            {/* Data shape */}
            <polygon
              points={points}
              fill="var(--nyt-accent)"
              fillOpacity="0.2"
              stroke="var(--nyt-accent)"
              strokeWidth="3"
              strokeLinejoin="round"
              className="radar-polygon transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1)"
            />

            {/* Interactive Points */}
            <g className="cursor-crosshair">
                <circle cx={x1} cy={y1} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px] cursor-pointer"
                  onMouseEnter={() => setActiveTooltip({x: x1, y: y1, label: labels.objectivity, value: `${objectivity.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
                <circle cx={x2} cy={y2} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px] cursor-pointer"
                  onMouseEnter={() => setActiveTooltip({x: x2, y: y2, label: labels.sensationalism, value: `${sensationalism.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
                <circle cx={x3} cy={y3} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px] cursor-pointer"
                  onMouseEnter={() => setActiveTooltip({x: x3, y: y3, label: labels.emotions, value: `${emotionalCharge.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
            </g>
          </svg>

          {/* HTML Tooltip Overlay */}
          <div
            className={`absolute z-20 pointer-events-none bg-zinc-900 text-white dark:bg-white dark:text-black px-3 py-2 rounded shadow-xl text-xs font-bold transition-all duration-200 whitespace-nowrap flex flex-col items-center ${activeTooltip ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}
            style={{
              left: activeTooltip ? `${(activeTooltip.x / 200) * 100}%` : '50%',
              top: activeTooltip ? `${(activeTooltip.y / 200) * 100}%` : '50%',
              transform: 'translate(-50%, -120%)'
            }}
          >
            <span className="uppercase text-[9px] tracking-widest opacity-80">{activeTooltip?.label}</span>
            <span className="text-sm">{activeTooltip?.value}</span>
          </div>
        </div>

        {/* Text Metrics */}
        <div className="flex-1 w-full space-y-6">
          <div className="text-center md:text-left">
            <span className="inline-block bg-nyt-accent/10 px-3 py-1 rounded text-[10px] font-black uppercase tracking-widest text-nyt-accent mb-3">{labels.mediaPulse}</span>
            <p className="text-2xl font-serif font-black leading-tight text-foreground">
              {labels.tone}: <span className={getSentimentColor(sentiment.score)}>{sentiment.tone}</span>
            </p>
          </div>

          <div className="flex flex-col gap-4 pt-4 border-t border-border">
            <div className="space-y-1.5 pulse-stat-row">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">{labels.objectivity}</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{objectivity.toFixed(0)}%</span>
              </div>
              <div className="h-2 w-full bg-secondary/40 rounded-full overflow-hidden border border-border/10 shadow-inner">
                  <div className="h-full bg-gradient-to-r from-zinc-700 to-zinc-950 dark:from-zinc-300 dark:to-white transition-all duration-1000 delay-300 rounded-full relative" style={{ width: isMounted ? `${objectivity}%` : '0%' }}>
                      <div className="absolute top-0 right-0 bottom-0 w-2 bg-white/40 blur-[1px] animate-pulse" />
                  </div>
              </div>
            </div>
            <div className="space-y-1.5 pulse-stat-row">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">{labels.sensationalism}</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{sensationalism.toFixed(0)}%</span>
              </div>
              <div className="h-2 w-full bg-secondary/40 rounded-full overflow-hidden border border-border/10 shadow-inner">
                  <div className="h-full bg-gradient-to-r from-nyt-red to-rose-400 transition-all duration-1000 delay-500 rounded-full relative" style={{ width: isMounted ? `${sensationalism}%` : '0%' }}>
                      <div className="absolute top-0 right-0 bottom-0 w-2 bg-white/40 blur-[1px] animate-pulse" />
                  </div>
              </div>
            </div>
            <div className="space-y-1.5 pulse-stat-row">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">{labels.emotionality}</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{emotionalCharge.toFixed(0)}%</span>
              </div>
              <div className="h-2 w-full bg-secondary/40 rounded-full overflow-hidden border border-border/10 shadow-inner">
                  <div className="h-full bg-gradient-to-r from-amber-500 to-amber-300 transition-all duration-1000 delay-700 rounded-full relative" style={{ width: isMounted ? `${emotionalCharge}%` : '0%' }}>
                      <div className="absolute top-0 right-0 bottom-0 w-2 bg-white/40 blur-[1px] animate-pulse" />
                  </div>
              </div>
            </div>
          </div>

          <p className="text-[10px] text-zinc-500 dark:text-zinc-400 font-medium leading-relaxed italic border-l-2 border-zinc-200 dark:border-zinc-800 pl-3 py-1">
            {labels.note}
          </p>
        </div>
      </div>
    </div>
  );
};
