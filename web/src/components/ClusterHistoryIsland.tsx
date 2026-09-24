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

export default function ClusterHistoryIsland({ clusterId, lang = 'mk' }: { clusterId: string, lang?: string }) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const isMK = lang === 'mk';

  const API_URL = apiBaseUrl();

  const fetchHistory = async () => {
    if (history.length > 0 || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/cluster/${clusterId}/history?lang=${lang}`);
      const data = await res.json();
      if (data.status === 'success') {
        setHistory(data.history || []);
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
        className="flex items-center gap-[var(--grid-gap)] text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground hover:text-nyt-accent transition-all group"
      >
        <div className="w-6 h-[1px] bg-border group-hover:bg-nyt-accent transition-colors" />
        <History size={11} className="group-hover:rotate-[-30deg] transition-transform" />
        {isMK ? 'РЕДАКЦИСКИ ЛОГ' : 'REDAKCIJSKI LOG'}
        {isOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>

      {isOpen && (
        <div className="mt-6 space-y-4 animate-in fade-in slide-in-from-top-2 duration-500">
          {loading ? (
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 animate-pulse">
                {isMK ? 'Архивски увид...' : 'Arhivski uvid...'}
            </p>
          ) : history.length === 0 ? (
            <div className="flex items-center gap-[var(--grid-gap)] p-4 border border-border/40 bg-secondary/5 rounded-sm">
                <Sparkles size={14} className="text-nyt-accent" />
                <span className="text-[11px] font-black uppercase tracking-widest text-foreground">
                    {isMK ? 'Нов наратив: Прва верзија на прегледот' : 'Nov narativ: Prva verzija sinteze'}
                </span>
            </div>
          ) : (
            <div className="space-y-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-4">
                    {isMK ? 'ЕВОЛУЦИЈА НА СТОРИЈАТА' : 'EVOLUCIJA PRIČE'}
                </p>
                {history.map((item, idx) => (
                <div key={idx} className="border border-border/60 bg-background shadow-sm hover:border-nyt-accent/30 transition-all">
                    <button
                    onClick={() => setExpandedIndex(expandedIndex === idx ? null : idx)}
                    className="w-full flex items-center justify-between p-4"
                    >
                    <div className="flex items-center gap-[var(--grid-gap)]">
                        <Clock size={12} className="text-muted-foreground/60" />
                        <span className="text-[11px] font-black tabular-nums text-foreground">
                            {new Date(item.created_at).toLocaleString(isMK ? 'mk-MK' : 'sr-RS', {
                                day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                            })}
                        </span>
                    </div>
                    <span className="text-[9px] font-black uppercase tracking-[0.1em] border border-border px-2 py-1 rounded-sm text-muted-foreground group-hover:text-nyt-accent transition-colors">
                        {isMK ? 'РЕВИЗИЈА' : 'REVIZIJA'} {history.length - idx}
                    </span>
                    </button>

                    {expandedIndex === idx && (
                    <div className="p-5 pt-0 animate-in fade-in duration-300">
                        <div className="prose-nyt text-[13px] leading-relaxed text-secondary-foreground font-serif italic border-l-2 border-border pl-4">
                        {(item.summary || '').split('\n').map((p, pi) => (
                            <p key={pi} className="mb-2 last:mb-0">{p}</p>
                        ))}
                        </div>
                    </div>
                    )}
                </div>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
