import { ArrowUpRight, Sparkles, User } from 'lucide-react';
import React from 'react';
import { HighlightMatch } from './HighlightMatch';
import { proxiedImage } from './utils';
import type { EntityResult, SearchAction, Suggestion, TFunction } from './types';

type SearchResultItemProps =
  | {
      type: 'ENTITY';
      data: EntityResult;
      query: string;
      isActive: boolean;
      onClick: () => void;
      itemRef: (el: HTMLElement | null) => void;
      navIndex: number;
      t?: TFunction;
    }
  | {
      type: 'CLUSTER';
      data: Suggestion;
      query: string;
      isActive: boolean;
      onClick: () => void;
      itemRef: (el: HTMLElement | null) => void;
      navIndex: number;
      t: TFunction;
    }
  | {
      type: 'ACTION';
      data: SearchAction;
      query: string;
      isActive: boolean;
      onClick: () => void;
      itemRef: (el: HTMLElement | null) => void;
      navIndex: number;
      t?: TFunction;
    };

export const SearchResultItem = React.memo(function SearchResultItem(props: SearchResultItemProps) {
  const { type, data, query, isActive, onClick, itemRef, navIndex } = props;

  const baseClass = `search-animate-item w-full flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-none border transition-all text-left`;
  const activeClass = isActive
    ? 'bg-secondary/80 border-border ring-1 ring-border'
    : 'bg-transparent border-transparent hover:bg-secondary/30';

  if (type === 'ENTITY') {
    const entity = data;
    return (
      <button
        ref={itemRef}
        onClick={onClick}
        data-active-nav={navIndex}
        className={`${baseClass} ${activeClass}`}
        style={{ animationDelay: '20ms' }}
      >
        <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-none overflow-hidden bg-secondary flex items-center justify-center shrink-0 border border-border">
          {entity.image_url ? (
            <img
              src={proxiedImage(entity.image_url, 128)}
              alt=""
              loading="lazy"
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={24} className="text-muted-foreground" />
          )}
        </div>
        <div>
          <p className="font-serif font-black text-lg sm:text-xl">
            <HighlightMatch text={entity.name} query={query} />
          </p>
          <p className="ui-label-min text-muted-foreground">
            {entity.type} · {entity.total_mentions} {props.t?.('search.mentions')}
          </p>
        </div>
        <ArrowUpRight size={16} className="ml-auto text-muted-foreground" />
      </button>
    );
  }

  if (type === 'CLUSTER') {
    const item = data;
    const t = props.t as TFunction;
    return (
      <button
        ref={itemRef}
        onClick={onClick}
        data-active-nav={navIndex}
        className={`${baseClass} group ${
          item.has_synthesis
            ? 'bg-amber-500/5 border-amber-500/10 hover:border-amber-500/30'
            : ''
        } ${isActive ? 'bg-secondary/80 border-border ring-1 ring-border' : ''}`}
        style={{ animationDelay: `${navIndex * 20}ms` }}
      >
        <div className="w-14 sm:w-16 aspect-[4/3] rounded-none overflow-hidden bg-secondary shrink-0 border border-border/50">
          {item.image_url && (
            <img
              src={proxiedImage(item.image_url, 200)}
              alt=""
              loading="lazy"
              className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className={`ui-label-min ${
                item.has_synthesis ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'
              }`}
            >
              {item.category}
            </span>
            {item.has_synthesis && (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-none bg-amber-500/10 text-amber-600 dark:text-amber-400 ui-label-min">
                <Sparkles size={8} fill="currentColor" />
                {t('search.synthesis')}
              </span>
            )}
          </div>
          <p className="font-serif font-black text-base sm:text-lg leading-tight line-clamp-2 group-hover:text-foreground transition-colors">
            <HighlightMatch text={item.title} query={query} />
          </p>
          {item.description && (
            <p className="mt-1 text-[12px] sm:text-[13px] text-muted-foreground line-clamp-2 leading-snug">
              <HighlightMatch text={item.description} query={query} />
            </p>
          )}
          <div className="flex items-center gap-2 sm:gap-[var(--grid-gap)] mt-1.5 sm:mt-2 ui-label-min text-muted-foreground/60">
            <span>{item.source}</span>
            <span>
              {item.sourceCount} {item.sourceCount === 1 ? t('news.source') : t('news.sources')}
            </span>
          </div>
        </div>
      </button>
    );
  }

  // ACTION
  const action = data;
  return (
    <button
      ref={itemRef}
      onClick={onClick}
      data-active-nav={navIndex}
      className={`${baseClass} ${activeClass}`}
      style={{ animationDelay: `${navIndex * 20}ms` }}
    >
      <div className="p-2 bg-secondary rounded-none text-muted-foreground">
        <action.icon size={16} />
      </div>
      <span className="search-cmd-action-title">{action.label}</span>
      <span className="hidden sm:inline ui-label-min text-muted-foreground opacity-60">
        → {action.href}
      </span>
    </button>
  );
});
