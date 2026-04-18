import React, { useEffect, useState } from 'react';
import { ArrowDown, ArrowRight, Calendar, Clock, History } from 'lucide-react';

interface TimelineItem {
  article_id: number;
  title: string;
  source: string;
  created_at: string;
  is_first: boolean;
  is_major: boolean;
  milestone?: string;
}

interface StorylineItem {
  cluster_id: string;
  title: string;
  first_seen: string;
  similarity: number;
}

interface StoryTimelineProps {
  timeline: TimelineItem[];
  clusterId: string;
  apiUrl: string;
}

const StoryTimeline: React.FC<StoryTimelineProps> = ({ timeline, clusterId, apiUrl }) => {
  const [history, setHistory] = useState<StorylineItem[]>([]);

  useEffect(() => {
    let cancelled = false;

    fetch(`${apiUrl}/intelligence/cluster/${clusterId}/history`)
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) setHistory(data.history || []);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });

    return () => {
      cancelled = true;
    };
  }, [clusterId, apiUrl]);

  if (!timeline || timeline.length === 0) return null;

  // Process timeline to find interesting points if milestone not provided
  const processedTimeline = timeline.map((item, index) => {
    let milestone = item.milestone;
    if (!milestone) {
        if (item.is_first) milestone = "ПОЧЕТОК";
        else if (index === Math.floor(timeline.length / 2) && timeline.length >= 4) milestone = "ДИВЕРГЕНЦИЈА";
        else if (index === timeline.length - 1 && timeline.length >= 3) milestone = "КОНСЕНЗУС";
    }
    return { ...item, milestone };
  });

  const getTimeStr = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const getDateStr = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('mk-MK', { day: 'numeric', month: 'short' });
    } catch {
      return '';
    }
  };

  return (
    <div className="story-timeline py-6">
      <div className="flex items-center gap-2 mb-10 border-b border-border pb-2">
        <History size={18} className="text-nyt-accent" />
        <h2 className="nyt-section-label text-nyt-accent tracking-[0.2em] mb-0">ЕВОЛУЦИЈА НА ПРИКАЗНАТА</h2>
      </div>

      <div className="relative border-l-2 border-border ml-3 pl-8 space-y-12">
        {processedTimeline.map((item, index) => (
          <div key={item.article_id} className="relative">
            {/* Milestone Badge */}
            {item.milestone && (
                <div className="absolute -left-[32px] -top-8 px-2 py-0.5 bg-background border border-nyt-accent text-[9px] font-black tracking-widest text-nyt-accent rounded">
                    {item.milestone}
                </div>
            )}

            {/* The dot */}
            <div className={`absolute -left-[41px] top-1.5 w-4 h-4 rounded-full border-2 border-background ${item.is_first ? 'bg-nyt-red scale-125' : item.milestone === 'КОНСЕНЗУС' ? 'bg-green-600' : 'bg-border'}`}>
              {item.is_first && <div className="absolute inset-0 rounded-full animate-ping bg-nyt-red opacity-20"></div>}
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                <span className="flex items-center gap-1 font-sans"><Clock size={10} /> {getTimeStr(item.created_at)}</span>
                <span>·</span>
                <span className="font-sans">{getDateStr(item.created_at)}</span>
                {item.is_first && <span className="text-nyt-red ml-2 bg-nyt-red/5 px-1.5 border border-nyt-red/20 font-sans">ПРВА ОБЈАВА</span>}
              </div>
              <h3 className={`font-serif leading-snug tracking-tight ${item.is_major || item.milestone ? 'text-lg font-black text-foreground' : 'text-base font-bold text-secondary-foreground opacity-80'}`}>
                {item.title}
              </h3>
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground font-sans">
                    Извор: <span className="text-foreground">{item.source}</span>
                </p>
                {item.milestone === 'ДИВЕРГЕНЦИЈА' && (
                    <span className="text-[9px] font-black bg-nyt-red/10 text-nyt-red px-2 py-0.5 rounded font-sans">РАЗЛИКИ ВО ИЗВЕСТУВАЊЕТО</span>
                )}
                {item.milestone === 'КОНСЕНЗУС' && (
                    <span className="text-[9px] font-black bg-green-600/10 text-green-600 px-2 py-0.5 rounded font-sans">ПОТВРДЕНИ ФАКТИ</span>
                )}
              </div>
            </div>
          </div>
        ))}

        {history.length > 0 && (
          <>
            <div className="relative -left-8 w-[calc(100%+2rem)] border-t border-border/80 pt-12" />
            {history.map((item) => (
              <div key={item.cluster_id} className="relative">
                <div className="absolute -left-[41px] top-1.5 z-10 h-4 w-4 rounded-full border-2 border-nyt-accent bg-background" />

                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                    <span className="flex items-center gap-1 font-sans">
                      <Calendar size={10} /> {getDateStr(item.first_seen)}
                    </span>
                    <span>·</span>
                    <span className="font-sans">Претходен кластер</span>
                  </div>
                  <a href={`/cluster/${item.cluster_id}`} className="group block">
                    <h3 className="font-serif text-base font-bold leading-snug tracking-tight text-secondary-foreground transition-colors group-hover:text-nyt-accent">
                      {item.title}
                    </h3>
                    <div className="mt-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-nyt-accent opacity-0 transition-opacity group-hover:opacity-100">
                      Види го кластерот <ArrowRight size={12} />
                    </div>
                  </a>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
      
      <div className="mt-12 flex justify-center">
        <div className="bg-secondary/30 px-6 py-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground border border-border rounded-full flex items-center gap-2 hover:bg-secondary/50 transition-colors cursor-default">
          <ArrowDown size={12} /> Крај на хронологијата
        </div>
      </div>
    </div>
  );
};

export default StoryTimeline;
