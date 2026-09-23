import React, { useEffect, useState } from 'react';
import { User, TrendingUp, Loader2 } from 'lucide-react';
import { useClientTranslations } from '../i18n/clientTranslations';
import { entity } from '../i18n/namespaces/entity';
import { localePathForLang } from '../lib/localePaths';

interface EntityContextCardProps {
  name: string;
  lang?: 'sr' | 'mk';
}

export default function EntityContextCard({ name, lang = 'mk' }: EntityContextCardProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const t = useClientTranslations(lang, entity);

  useEffect(() => {
    fetch(`/api/entity-graph/${encodeURIComponent(name)}`)
      .then(res => res.json())
      .then(json => {
        if (json.status === 'success') setData(json.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [name]);

  if (loading) return <div className="p-4 bg-background border border-border flex items-center gap-[var(--grid-gap)]"><Loader2 className="animate-spin text-presek-mark" size={14} /> <span className="text-[10px] uppercase font-black">{t('entity.loading')}</span></div>;
  if (!data) return null;

  return (
    <div className="group relative">
        <div className="flex items-center gap-[var(--grid-gap)] px-3 py-1.5 bg-secondary/30 border border-border rounded-sm hover:border-presek-mark transition-colors cursor-help">
            <User size={12} className="text-presek-mark" />
            <span className="text-[11px] font-bold uppercase tracking-tight">{name}</span>
            <div className="ml-2 w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" title={t('entity.active_subject')}></div>
        </div>

        {/* Hover Popover */}
        <div className="absolute bottom-full left-0 mb-3 w-64 bg-background border-2 border-foreground shadow-2xl opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all z-50 pointer-events-none group-hover:pointer-events-auto">
            <div className="p-4">
                <div className="flex justify-between items-start mb-3 pb-2 border-b border-border">
                    <span className="text-[9px] font-black uppercase tracking-[0.2em] text-presek-mark">{t('entity.context_card')}</span>
                    <div className="flex items-center gap-1.5 bg-secondary px-2 py-0.5 rounded-full">
                        <TrendingUp size={10} />
                        <span className="text-[9px] font-black">{data.importance_score}</span>
                    </div>
                </div>

                <h4 className="font-serif font-black text-lg mb-2">{name}</h4>
                <p className="text-xs font-nyt-body leading-relaxed text-secondary-foreground mb-4">
                    {data.bio_summary || t('entity.bio_summary')}
                </p>

                <div className="flex items-center justify-between pt-3 border-t border-border">
                    <span className="text-[8px] font-black uppercase text-muted-foreground tracking-widest">{t('entity.last_seen')} {new Date(data.last_seen).toLocaleDateString(lang === 'sr' ? 'sr-RS' : 'mk-MK')}</span>
                    <a href={localePathForLang(`/subjekt/${encodeURIComponent(name)}`, lang)} className="text-[9px] font-black uppercase text-presek-mark border-b border-presek-mark">{t('entity.profile')}</a>
                </div>
            </div>
            {/* Pointer notch */}
            <div className="absolute top-full left-6 w-3 h-3 bg-background border-r-2 border-b-2 border-foreground rotate-45 -translate-y-1.5"></div>
        </div>
    </div>
  );
}
