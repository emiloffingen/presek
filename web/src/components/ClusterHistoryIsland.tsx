import React, { useState, useEffect } from 'react';
import { History, Clock, ChevronDown, ChevronUp, Sparkles, BookOpen } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

interface HistoryItem {
  summary: string;
  generated_article: string;
  created_at: string;
  perspectives: any[];
  verification_report: any;
}

export default function ClusterHistoryIsland({ clusterId }: { clusterId: string }) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const API_URL = apiBaseUrl();

  const fetchHistory = async () => {
    if (history.length > 0 || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/cluster/${clusterId}/history`);
      const data = await res.json();
      if (data.status === 'success') {
        setHistory(data.history);
      }
    } catch (e) {
      console.error('History fetch failed', e);
    } finally {
      setLoading(false);
    }
  };

  const toggleOpen = () => {
    if (!isOpen) fetchHistory();
    setIsOpen(!isOpen);
  };

  if (loading && !isOpen) return null;

  return (
    <div className="mt-8 border-t border-border pt-6">
      <button 
        onClick={toggleOpen}
        className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-nyt-accent transition-colors"
      >
        <History size={12} />
        ИСТОРИЈА НА СИНТЕЗИ
        {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {isOpen && (
        <div className="mt-6 space-y-4 motion-rise">
          {loading ? (
            <p className="text-[10px] italic text-muted-foreground">Се вчитува архивата...</p>
          ) : history.length === 0 ? (
            <p className="text-[10px] italic text-muted-foreground">Нема претходни верзии за оваа сторија.</p>
          ) : (
            history.map((item, idx) => (
              <div key={idx} className="border border-border bg-secondary/5 rounded-lg overflow-hidden">
                <button 
                  onClick={() => setExpandedIndex(expandedIndex === idx ? null : idx)}
                  className="w-full flex items-center justify-between p-3 hover:bg-secondary/10 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Clock size={11} className="text-muted-foreground" />
                    <span className="text-[10px] font-bold text-foreground">
                        {new Date(item.created_at).toLocaleString('mk-MK', { 
                            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' 
                        })}
                    </span>
                  </div>
                  <span className="text-[9px] font-black uppercase tracking-tighter bg-border px-1.5 py-0.5 rounded">ВЕРЗИЈА {history.length - idx}</span>
                </button>
                
                {expandedIndex === idx && (
                  <div className="p-4 border-t border-border bg-background/50">
                    <div className="prose-nyt text-sm leading-relaxed text-muted-foreground font-serif italic">
                       {item.summary.split('\n').map((p, pi) => (
                         <p key={pi} className="mb-2">{p}</p>
                       ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
