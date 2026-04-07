import React from 'react';
import { Clock, History, ArrowDown } from 'lucide-react';

interface TimelineItem {
  article_id: number;
  title: string;
  source: string;
  created_at: string;
  is_first: boolean;
  is_major: boolean;
}

interface StoryTimelineProps {
  timeline: TimelineItem[];
}

const StoryTimeline: React.FC<StoryTimelineProps> = ({ timeline }) => {
  if (!timeline || timeline.length === 0) return null;

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
      <div className="flex items-center gap-2 mb-8 border-b border-border pb-2">
        <History size={18} className="text-nyt-accent" />
        <h2 className="nyt-section-label text-nyt-accent tracking-[0.2em] mb-0">ХРОНОЛОГИЈА НА НАСТАНОТ</h2>
      </div>

      <div className="relative border-l-2 border-border ml-3 pl-8 space-y-8">
        {timeline.map((item, index) => (
          <div key={item.article_id} className="relative">
            {/* The dot */}
            <div className={`absolute -left-[41px] top-1.5 w-4 h-4 rounded-full border-2 border-background ${item.is_first ? 'bg-nyt-red scale-125' : 'bg-border'}`}>
              {item.is_first && <div className="absolute inset-0 rounded-full animate-ping bg-nyt-red opacity-20"></div>}
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                <span className="flex items-center gap-1"><Clock size={10} /> {getTimeStr(item.created_at)}</span>
                <span>·</span>
                <span>{getDateStr(item.created_at)}</span>
                {item.is_first && <span className="text-nyt-red ml-2 bg-nyt-red/5 px-1.5 border border-nyt-red/20">Оригинална објава</span>}
                {item.is_major && !item.is_first && <span className="text-foreground border border-border px-1.5">Клучен развој</span>}
              </div>
              <h3 className={`font-serif leading-snug ${item.is_major ? 'text-lg font-black text-foreground' : 'text-base font-bold text-secondary-foreground opacity-80'}`}>
                {item.title}
              </h3>
              <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
                Извор: <span className="text-foreground">{item.source}</span>
              </p>
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-8 flex justify-center">
        <div className="bg-surface-soft px-4 py-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground border border-border rounded-full flex items-center gap-2">
          <ArrowDown size={12} /> Крај на тековниот преглед
        </div>
      </div>
    </div>
  );
};

export default StoryTimeline;
