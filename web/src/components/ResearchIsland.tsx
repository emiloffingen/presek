import React, { useState } from 'react';
import { Sparkles, BrainCircuit, BarChart3, Users, BookOpen, Loader2, X, ChevronRight, CheckCircle2 } from 'lucide-react';

interface ResearchIslandProps {
  clusterId: string;
  initialHeadline: string;
}

type ResearchMode = 'facts' | 'perspectives' | 'context';

export default function ResearchIsland({ clusterId, initialHeadline }: ResearchIslandProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<ResearchMode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const performResearch = async (mode: ResearchMode) => {
    setLoading(mode);
    setError(null);
    try {
      const resp = await fetch(`/api/intelligence/cluster/${clusterId}/analyst?mode=${mode}`);
      const result = await resp.json();
      if (result.status === 'success') {
        setData(result);
      } else {
        setError(result.message || 'Грешка при анализата.');
      }
    } catch (e) {
      setError('Аналитичарот моментално не е достапен.');
    } finally {
      setLoading(null);
    }
  };

  const modes = [
    { id: 'facts' as const, label: 'Бројки и Факти', icon: BarChart3, desc: 'Извлечи статистички податоци и клучни бројки.' },
    { id: 'perspectives' as const, label: 'Ставови и Изјави', icon: Users, desc: 'Кој што рекол и какви се реакциите.' },
    { id: 'context' as const, label: 'Широк Контекст', icon: BookOpen, desc: 'Зошто ова е важно за општеството.' },
  ];

  return (
    <div className="ai-analyst-container mt-12 mb-20">
      <div className="flex items-center gap-3 mb-8">
        <BrainCircuit className="text-nyt-accent" size={24} />
        <h2 className="font-serif font-black text-2xl md:text-3xl text-foreground">AI Истражувачки Центар</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => performResearch(m.id)}
            disabled={!!loading}
            className={`group relative p-6 text-left border border-border rounded-xl bg-secondary/10 transition-all hover:bg-background hover:shadow-xl hover:border-nyt-accent/30 ${loading === m.id ? 'ring-2 ring-nyt-accent' : ''}`}
          >
            <div className={`p-3 rounded-lg mb-4 inline-block ${loading === m.id ? 'bg-nyt-accent text-white' : 'bg-secondary/30 text-muted-foreground group-hover:bg-nyt-accent/10 group-hover:text-nyt-accent'}`}>
              {loading === m.id ? <Loader2 className="animate-spin" size={20} /> : <m.icon size={20} />}
            </div>
            <h4 className="font-bold text-sm mb-2 uppercase tracking-wide group-hover:text-nyt-accent transition-colors">{m.label}</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">{m.desc}</p>
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-6 p-4 border border-red-500/20 bg-red-500/5 text-red-600 dark:text-red-400 text-xs rounded-lg flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      {data && (
        <div className="mt-8 editorial-panel p-0 overflow-hidden border-nyt-accent/40 motion-rise shadow-2xl">
          <div className="bg-nyt-accent px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-white">
              <Sparkles size={14} fill="currentColor" />
              <span className="text-[10px] font-black uppercase tracking-[0.2em]">
                {modes.find(m => m.id === data.mode)?.label} · Пресек Анализа
              </span>
            </div>
            <button onClick={() => setData(null)} className="text-white/60 hover:text-white"><X size={16} /></button>
          </div>
          
          <div className="p-8 md:p-12 bg-background/50 relative">
             <div className="prose-nyt max-w-none prose-p:text-lg md:prose-p:text-xl prose-p:leading-relaxed">
                {data.report.split('\n').map((line: string, i: number) => {
                    const trimmed = line.trim();
                    if (!trimmed) return <div key={i} className="h-4" />;
                    if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
                        return <li key={i} className="ml-4 mb-3 list-none flex gap-3 text-foreground/90"><span className="text-nyt-accent mt-1.5"><CheckCircle2 size={14} /></span> <span>{trimmed.replace(/^[-•]\s*/, '')}</span></li>;
                    }
                    if (trimmed.startsWith('#')) return <h3 key={i} className="font-serif font-black text-2xl mt-8 mb-4 border-b border-border pb-2">{trimmed.replace(/^#+\s*/, '')}</h3>;
                    return <p key={i} className="mb-4 text-foreground/90 font-nyt-body leading-relaxed">{trimmed}</p>;
                })}
             </div>
             
             <div className="mt-12 pt-8 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground italic uppercase tracking-wider">
                   Извор: Внатрешна AI анализа на целосната содржина.
                </div>
                <span className="text-[9px] text-nyt-accent font-black tracking-widest border border-nyt-accent/20 px-2 py-1 rounded">
                   MISTRAL INSIGHT v4.0
                </span>
             </div>
          </div>
        </div>
      )}
    </div>
  );
}
