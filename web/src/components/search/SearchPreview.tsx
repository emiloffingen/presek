import { Activity, ChevronRight, Clock, ExternalLink, Layout, Sparkles, User } from 'lucide-react';
import React from 'react';
import { proxiedImage } from './utils';
import type { EntityResult, SearchAction, Suggestion, TFunction } from './types';

type SearchPreviewProps = {
  item: { type: 'ENTITY'; data: EntityResult } | { type: 'CLUSTER'; data: Suggestion } | { type: 'ACTION'; data: SearchAction } | null;
  t: TFunction;
  onOpenCluster: (id: string) => void;
  onOpenEntity: (name: string) => void;
  onOpenAction: (href: string) => void;
};

export const SearchPreview = React.memo(function SearchPreview({
  item,
  t,
  onOpenCluster,
  onOpenEntity,
  onOpenAction,
}: SearchPreviewProps) {
  return (
    <div className="hidden lg:flex w-[400px] bg-secondary/5 border-l border-border/40 p-8 flex-col overflow-y-auto">
      {item ? (
        <div className="animate-in fade-in slide-in-from-right-4 duration-300">
          {item.type === 'CLUSTER' && <ClusterPreview data={item.data} t={t} onOpen={onOpenCluster} />}
          {item.type === 'ENTITY' && <EntityPreview data={item.data} t={t} onOpen={onOpenEntity} />}
          {item.type === 'ACTION' && <ActionPreview data={item.data} t={t} onOpen={onOpenAction} />}
        </div>
      ) : (
        <div className="h-full flex flex-col items-center justify-center text-center opacity-30 select-none">
          <div className="w-20 h-20 border-2 border-dashed border-muted-foreground rounded-full flex items-center justify-center mb-6">
            <Layout size={32} />
          </div>
          <p className="font-serif font-black text-xl mb-1">{t('search.preview_title')}</p>
          <p className="ui-label-min">{t('search.preview_hint')}</p>
        </div>
      )}
    </div>
  );
});

function ClusterPreview({
  data,
  t,
  onOpen,
}: {
  data: Suggestion;
  t: TFunction;
  onOpen: (id: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="aspect-[16/9] rounded-none overflow-hidden bg-secondary border border-border shadow-sm">
        {data.image_url && (
          <img
            src={proxiedImage(data.image_url, 600)}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover"
          />
        )}
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          {data.category && (
            <span className="px-2 py-1 bg-foreground text-background search-cmd-preview-badge rounded">
              {data.category}
            </span>
          )}
          {data.has_synthesis && (
            <span className="px-2 py-1 bg-gradient-to-r from-amber-500 to-amber-600 text-white search-cmd-preview-badge rounded flex items-center gap-1 shadow-sm shadow-amber-500/20">
              <Sparkles size={10} fill="currentColor" />
              {t('search.synthesis')}
            </span>
          )}
          {data.created_at && !isNaN(new Date(data.created_at).getTime()) && (
            <span className="ui-kicker text-muted-foreground flex items-center gap-1">
              <Clock size={12} /> {new Date(data.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
        <h2 className="font-serif font-black text-2xl leading-tight mb-4">{data.title}</h2>
        <p className="text-base text-muted-foreground leading-relaxed font-nyt-body line-clamp-6">
          {data.description}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-[var(--grid-gap)] py-6 border-y border-border/40">
        <div>
          <p className="ui-kicker text-muted-foreground mb-1">{t('search.sources_label')}</p>
          <p className="text-xl font-black">{data.sourceCount}</p>
        </div>
        {typeof data.pulse_score === 'number' && (
          <div>
            <p className="ui-kicker text-muted-foreground mb-1">{t('search.score_label')}</p>
            <p className="text-xl font-black text-muted-foreground">{data.pulse_score}</p>
          </div>
        )}
      </div>

      <button
        onClick={() => onOpen(data.cluster_id)}
        className="search-cmd-cta w-full py-4 bg-foreground text-background rounded-none shadow-lg hover:scale-[1.02] transition-all flex items-center justify-center gap-[var(--grid-gap)]"
      >
        {t('search.open_story')} <ChevronRight size={16} />
      </button>
    </div>
  );
}

function EntitySentiment({
  data,
  t,
}: {
  data: EntityResult;
  t: TFunction;
}) {
  const score = data.sentiment_score;
  let sentimentKey: string;
  let colorClass: string;
  let iconColorClass: string;

  if (score >= 0.1) {
    sentimentKey = 'search.sentiment_positive';
    colorClass = 'text-emerald-600';
    iconColorClass = 'text-emerald-500';
  } else if (score <= -0.1) {
    sentimentKey = 'search.sentiment_negative';
    colorClass = 'text-red-600';
    iconColorClass = 'text-red-500';
  } else {
    sentimentKey = 'search.sentiment_neutral';
    colorClass = 'text-muted-foreground';
    iconColorClass = 'text-muted-foreground';
  }

  return (
    <div className="p-4 bg-background border border-border rounded-none flex items-center justify-between">
      <div>
        <p className="ui-kicker text-muted-foreground mb-1">{t('search.sentiment_label')}</p>
        <p className={`font-serif font-black text-lg ${colorClass}`}>{t(sentimentKey)}</p>
      </div>
      <Activity size={24} className={iconColorClass} />
    </div>
  );
}

function EntityPreview({
  data,
  t,
  onOpen,
}: {
  data: EntityResult;
  t: TFunction;
  onOpen: (name: string) => void;
}) {
  return (
    <div className="space-y-8">
      <div className="flex flex-col items-center text-center">
        <div className="w-32 h-32 rounded-full overflow-hidden border-4 border-border mb-6 bg-secondary flex items-center justify-center">
          {data.image_url ? (
            <img
              src={proxiedImage(data.image_url, 256)}
              alt=""
              loading="lazy"
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={64} className="text-muted-foreground/40" />
          )}
        </div>
        <h2 className="font-serif font-black text-3xl mb-2">{data.name}</h2>
        <p className="px-4 py-1.5 bg-secondary border border-border rounded-none ui-label-min text-muted-foreground">
          {data.type}
        </p>
      </div>

      <div className="space-y-4">
        <div className="p-4 bg-background border border-border rounded-none">
          <p className="ui-kicker text-muted-foreground mb-3">{t('search.media_presence')}</p>
          <p className="text-3xl font-black mb-3">{data.total_mentions}</p>
          <div className="w-full h-2 bg-muted rounded-sm overflow-hidden">
            <div
              className="h-full bg-foreground rounded-sm"
              style={{ width: `${Math.min(100, Math.max(5, (data.total_mentions / 1000) * 100))}%` }}
            />
          </div>
          <p className="text-xs font-bold mt-3 text-muted-foreground">
            {data.total_mentions} {t('search.mentions_in_archive')}
          </p>
        </div>

        <EntitySentiment data={data} t={t} />
      </div>

      <button
        onClick={() => onOpen(data.name)}
        className="search-cmd-cta w-full py-4 bg-foreground text-background rounded-none hover:opacity-90 transition-all flex items-center justify-center gap-[var(--grid-gap)]"
      >
        {t('search.view_all_stories')} <ExternalLink size={16} />
      </button>
    </div>
  );
}

function ActionPreview({
  data,
  t,
  onOpen,
}: {
  data: SearchAction;
  t: TFunction;
  onOpen: (href: string) => void;
}) {
  return (
    <div className="h-full flex flex-col justify-center items-center text-center space-y-6">
      <div className="w-24 h-24 bg-secondary rounded-none flex items-center justify-center text-muted-foreground rotate-3">
        <data.icon size={48} />
      </div>
      <div>
        <h2 className="font-serif font-black text-3xl mb-2">{data.label}</h2>
        <p className="text-muted-foreground text-sm max-w-[280px] leading-relaxed">{data.desc}</p>
      </div>
      <button
        onClick={() => onOpen(data.href)}
        className="search-cmd-cta px-10 py-4 bg-foreground text-background rounded-none hover:opacity-90 transition-all"
      >
        {t('search.open')}
      </button>
    </div>
  );
}
