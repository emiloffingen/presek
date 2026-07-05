import { navigate } from 'astro:transitions/client';
import { History, Search, TrendingUp, Zap, ArrowUpRight, X, Trash2 } from 'lucide-react';
import React from 'react';
import { SearchSkeleton } from './SearchSkeleton';
import { SearchResultItem } from './SearchResultItem';
import type {
  EntityResult,
  RecentSearch,
  SearchAction,
  Suggestion,
  TrendingItem,
  TFunction,
} from './types';

type SearchResultsProps = {
  query: string;
  isLoading: boolean;
  suggestions: Suggestion[];
  entityResult: EntityResult | null;
  filteredActions: SearchAction[];
  searchActions: SearchAction[];
  recentSearches: RecentSearch[];
  trendingItems: TrendingItem[];
  activeIndex: number;
  registerNavRef: (index: number, el: HTMLElement | null) => void;
  onSearchAll: () => void;
  onNavigateToCluster: (id: string) => void;
  onNavigateToQuery: (q: string) => void;
  onSetQuery: (q: string) => void;
  onRemoveRecentSearch: (q: string) => void;
  onClearRecentSearches?: () => void;
  searchTime?: number | null;
  closeSearch: () => void;
  t: TFunction;
  scrollRef: React.RefObject<HTMLDivElement | null>;
};

export const SearchResults = React.memo(function SearchResults({
  query,
  isLoading,
  suggestions,
  entityResult,
  filteredActions,
  searchActions,
  recentSearches,
  trendingItems,
  activeIndex,
  registerNavRef,
  onSearchAll,
  onNavigateToCluster,
  onNavigateToQuery,
  onSetQuery,
  onRemoveRecentSearch,
  onClearRecentSearches,
  searchTime,
  closeSearch,
  t,
  scrollRef,
}: SearchResultsProps) {
  const trimmedQuery = query.trim();

  const actionOffset = (entityResult ? 1 : 0) + suggestions.length;

  return (
    <div
      ref={scrollRef}
      data-testid="search-results"
      className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 sm:space-y-8 scroll-smooth lg:border-r lg:border-border/40 custom-scrollbar"
    >
      {/* Empty State / Initial View */}
      {!trimmedQuery && (
        <div className="space-y-6 sm:space-y-10">
          {recentSearches.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-3 sm:mb-4">
                <h3 className="ui-kicker flex items-center gap-[var(--grid-gap)] mb-0">
                  <History size={12} /> {t('search.recent_searches')}
                </h3>
                {onClearRecentSearches && (
                  <button
                    onClick={onClearRecentSearches}
                    className="text-[10px] font-bold text-muted-foreground/60 hover:text-foreground transition-colors flex items-center gap-1 cursor-pointer"
                    type="button"
                  >
                    <Trash2 size={10} />
                    {t('search.clear_all')}
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {recentSearches.map((s, i) => (
                  <div
                    key={i}
                    onClick={() => onSetQuery(s.query)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary/50 hover:bg-secondary border border-border/50 rounded-none text-[11px] sm:text-xs font-bold transition-all cursor-pointer group/pill"
                  >
                    <span>{s.query}</span>
                    <button
                      onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                        e.stopPropagation();
                        onRemoveRecentSearch(s.query);
                      }}
                      className="p-0.5 rounded-full hover:bg-muted-foreground/20 text-muted-foreground/40 hover:text-muted-foreground/80 transition-colors"
                      title={t('search.remove_search')}
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section>
            <h3 className="ui-kicker mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
              <TrendingUp size={12} /> {t('search.trending_topics')}
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 sm:gap-[var(--grid-gap)]">
              {trendingItems.length > 0 ? (
                trendingItems.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => onSetQuery(item.word)}
                    className="flex items-center gap-2 sm:gap-[var(--grid-gap)] p-2.5 sm:p-3 bg-secondary/30 hover:bg-secondary/60 rounded-none transition-all group text-left"
                  >
                    <span className="ui-label-min text-muted-foreground/50 group-hover:text-foreground">
                      {(i + 1).toString().padStart(2, '0')}
                    </span>
                    <span className="font-serif font-black text-[13px] sm:text-sm truncate">
                      {item.word}
                    </span>
                  </button>
                ))
              ) : (
                [1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="h-12 bg-secondary/20 animate-pulse rounded-none" />
                ))
              )}
            </div>
          </section>

          <section>
            <h3 className="ui-kicker mb-3 sm:mb-4 flex items-center gap-[var(--grid-gap)]">
              <Zap size={12} /> {t('search.quick_actions')}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-[var(--grid-gap)]">
              {searchActions.map((action, i) => (
                <button
                  key={action.id}
                  onClick={() => {
                    closeSearch();
                    navigate(action.href);
                  }}
                  className="search-animate-item flex items-center gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 bg-secondary/30 hover:bg-secondary/60 border border-border/50 rounded-none transition-all group text-left w-full"
                  style={{ animationDelay: `${i * 20}ms` }}
                >
                  <div className="p-2 bg-background rounded-none text-muted-foreground group-hover:text-foreground group-hover:bg-secondary transition-all">
                    <action.icon size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between w-full">
                      <p className="search-cmd-action-title">{action.label}</p>
                      <kbd className="hidden sm:inline px-1.5 py-0.5 bg-background border border-border/80 text-[9px] font-bold text-muted-foreground rounded-md shadow-sm">
                        {i + 1}
                      </kbd>
                    </div>
                    <p className="ui-label-min text-muted-foreground line-clamp-1">{action.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* One-character hint */}
      {trimmedQuery.length === 1 && (
        <div className="py-10 sm:py-14 flex flex-col items-center text-center text-muted-foreground">
          <Search size={28} className="mb-4 opacity-30" />
          <p className="text-sm sm:text-base max-w-sm">{t('search.type_more')}</p>
        </div>
      )}

      {/* Results List */}
      {trimmedQuery.length >= 2 && (
        <div className="space-y-6 sm:space-y-8">
          {!isLoading && searchTime !== undefined && searchTime !== null && suggestions.length > 0 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground/80 px-1 border-b border-border/20 pb-2">
              <span className="font-serif italic">
                {t('search.stats_timing', { count: suggestions.length + (entityResult ? 1 : 0), time: searchTime })}
              </span>
              <span className="text-[10px] opacity-60 font-bold uppercase tracking-wider">
                {t('search.global_search')}
              </span>
            </div>
          )}

          {!isLoading && (
            <button
              type="button"
              ref={(el) => registerNavRef(-1, el)}
              onClick={onSearchAll}
              data-active-nav="-1"
              className={`search-animate-item w-full flex items-center gap-3 p-3 sm:p-4 rounded-none border transition-all text-left ${
                activeIndex === -1
                  ? 'bg-secondary/80 border-border ring-1 ring-border'
                  : 'bg-secondary/20 border-border/50 hover:bg-secondary/40'
              }`}
            >
              <Search size={18} className="text-muted-foreground shrink-0" />
              <span className="search-cmd-action-title text-foreground">
                {t('search.search_all', { query: trimmedQuery })}
              </span>
              <ArrowUpRight size={16} className="ml-auto text-muted-foreground shrink-0" />
            </button>
          )}

          {isLoading ? (
            <SearchSkeleton />
          ) : (
            <>
              {entityResult && (
                <section>
                  <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.subjects')}</h3>
                  <SearchResultItem
                    type="ENTITY"
                    data={entityResult}
                    query={query}
                    isActive={activeIndex === 0}
                    onClick={() => onNavigateToQuery(entityResult.name)}
                    itemRef={(el) => registerNavRef(0, el)}
                    navIndex={0}
                    t={t}
                  />
                </section>
              )}

              {suggestions.length > 0 && (
                <section>
                  <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.stories')}</h3>
                  <div className="space-y-2">
                    {suggestions.map((item, idx) => {
                      const globalIdx = entityResult ? idx + 1 : idx;
                      return (
                        <SearchResultItem
                          key={item.cluster_id}
                          type="CLUSTER"
                          data={item}
                          query={query}
                          isActive={activeIndex === globalIdx}
                          onClick={() => onNavigateToCluster(item.cluster_id)}
                          itemRef={(el) => registerNavRef(globalIdx, el)}
                          navIndex={globalIdx}
                          t={t}
                        />
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          )}

          {filteredActions.length > 0 && (
            <section>
              <h3 className="ui-kicker mb-3 sm:mb-4">{t('search.actions')}</h3>
              <div className="grid grid-cols-1 gap-[var(--grid-gap)]">
                {filteredActions.map((action, idx) => {
                  const globalIdx = actionOffset + idx;
                  return (
                    <SearchResultItem
                      key={action.id}
                      type="ACTION"
                      data={action}
                      query={query}
                      isActive={activeIndex === globalIdx}
                      onClick={() => {
                        closeSearch();
                        navigate(action.href);
                      }}
                      itemRef={(el) => registerNavRef(globalIdx, el)}
                      navIndex={globalIdx}
                    />
                  );
                })}
              </div>
            </section>
          )}

          {!isLoading && suggestions.length === 0 && !entityResult && filteredActions.length === 0 && (
            <div className="py-14 sm:py-20 flex flex-col items-center text-center">
              <div className="w-14 h-14 sm:w-16 sm:h-16 bg-secondary/50 rounded-none flex items-center justify-center mb-5 sm:mb-6">
                <Search size={32} className="text-muted-foreground/30" />
              </div>
              <h4 className="font-serif font-black text-xl sm:text-2xl mb-2">
                {t('search.no_results_title', { query })}
              </h4>
              <p className="text-muted-foreground text-[13px] sm:text-sm max-w-xs">
                {t('search.no_results_desc')}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
