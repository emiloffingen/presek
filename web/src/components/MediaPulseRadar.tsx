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
  const [activeTooltip, setActiveTooltip] = React.useState<{x: number, y: number, label: string, value: string} | null>(null);

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
    <div className="media-pulse-card bg-background/60 backdrop-blur-md border border-nyt-accent/15 p-5 md:p-6 rounded-xl shadow-editorial overflow-hidden">
      <div className="flex flex-col gap-6 md:gap-8 items-center">
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
            <text x="100" y={cy - radius - 15} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">Objektivnost</text>
            <text x={cx + radius * Math.sin(120 * Math.PI / 180) + 18} y={cy - radius * Math.cos(120 * Math.PI / 180) + 18} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">Senzacionalizam</text>
            <text x={cx + radius * Math.sin(240 * Math.PI / 180) - 18} y={cy - radius * Math.cos(240 * Math.PI / 180) + 18} textAnchor="middle" className="text-[11px] font-black fill-muted-foreground uppercase tracking-[0.2em]">Emocije</text>

            {/* Data shape */}
            <polygon
              points={points}
              fill="var(--nyt-accent)"
              fillOpacity="0.2"
              stroke="var(--nyt-accent)"
              strokeWidth="3"
              strokeLinejoin="round"
              className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1)"
            />

            {/* Interactive Points */}
            <g className="cursor-crosshair">
                <circle cx={x1} cy={y1} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px]"
                  onMouseEnter={() => setActiveTooltip({x: x1, y: y1, label: 'Objektivnost', value: `${objectivity.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
                <circle cx={x2} cy={y2} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px]"
                  onMouseEnter={() => setActiveTooltip({x: x2, y: y2, label: 'Senzacionalizam', value: `${sensationalism.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
                <circle cx={x3} cy={y3} r="6" fill="var(--nyt-accent)" className="transition-all duration-[1200ms] cubic-bezier(0.16, 1, 0.3, 1) stroke-[4px] stroke-background hover:scale-150 hover:stroke-[2px]"
                  onMouseEnter={() => setActiveTooltip({x: x3, y: y3, label: 'Emocije', value: `${emotionalCharge.toFixed(1)}%`})} onMouseLeave={() => setActiveTooltip(null)} />
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
            <span className="inline-block bg-nyt-accent/10 px-3 py-1 rounded text-[10px] font-black uppercase tracking-widest text-nyt-accent mb-3">Mediumski Puls</span>
            <p className="text-2xl font-serif font-black leading-tight text-foreground">
              Ton: <span className={getSentimentColor(sentiment.score)}>{sentiment.tone}</span>
            </p>
          </div>

          <div className="flex flex-col gap-4 pt-4 border-t border-border">
            <div className="space-y-1.5">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">Objektivnost</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{objectivity.toFixed(0)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                  <div className="h-full bg-foreground transition-all duration-1000 delay-300" style={{ width: isMounted ? `${objectivity}%` : '0%' }}></div>
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">Senzacionalizam</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{sensationalism.toFixed(0)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                  <div className="h-full bg-nyt-red transition-all duration-1000 delay-500" style={{ width: isMounted ? `${sensationalism}%` : '0%' }}></div>
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between items-end">
                <span className="text-[10px] font-black uppercase text-muted-foreground tracking-[0.15em]">Emocionalnost</span>
                <span className="text-lg font-black tabular-nums tracking-tighter">{emotionalCharge.toFixed(0)}%</span>
              </div>
              <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
                  <div className="h-full bg-amber-500 transition-all duration-1000 delay-700" style={{ width: isMounted ? `${emotionalCharge}%` : '0%' }}></div>
              </div>
            </div>
          </div>

          <p className="text-[10px] text-zinc-500 dark:text-zinc-400 font-medium leading-relaxed italic border-l-2 border-zinc-200 dark:border-zinc-800 pl-3 py-1">
            * ova analiza e generirana avtomatski preku sporedba na jazicnite formi i strukturata na izvestuvanje kaj site vkluceni mediumi.
          </p>
        </div>
      </div>
    </div>
  );
};
