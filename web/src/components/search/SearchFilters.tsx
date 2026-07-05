import {
  Globe,
  Flag,
  Building2,
  TrendingUp,
  Trophy,
  Film,
  Cpu,
  type LucideIcon,
} from 'lucide-react';
import type { CategoryOption, TimespanOption, TFunction } from './types';

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  all: Globe,
  country: Flag,
  politics: Building2,
  economy: TrendingUp,
  sports: Trophy,
  culture: Film,
  technology: Cpu,
};

type SearchFiltersProps = {
  showFilters: boolean;
  categoryFilter: string;
  onCategoryChange: (id: string) => void;
  timespan: string;
  onTimespanChange: (id: string) => void;
  categories: CategoryOption[];
  timespans: TimespanOption[];
  t: TFunction;
};

export function SearchFilters({
  showFilters,
  categoryFilter,
  onCategoryChange,
  timespan,
  onTimespanChange,
  categories,
  timespans,
  t,
}: SearchFiltersProps) {
  if (!showFilters) return null;

  return (
    <div className="px-4 py-3 sm:px-6 sm:py-4 border-b border-border/40 bg-secondary/15 flex flex-col md:flex-row gap-4 md:items-center animate-in slide-in-from-top-4 duration-300">
      {/* Category Filter */}
      <div className="flex-1">
        <span className="ui-kicker text-muted-foreground block mb-2">{t('search.topic_label')}</span>
        <div className="flex flex-wrap gap-1.5">
          {categories.map((cat) => {
            const Icon = CATEGORY_ICONS[cat.id] || Globe;
            return (
              <button
                key={cat.id}
                data-testid="search-category-chip"
                data-category={cat.id}
                onClick={() => onCategoryChange(cat.id)}
                className={`search-cmd-chip px-3 py-1 sm:py-1.5 rounded-none transition-all border flex items-center gap-1.5 ${
                  categoryFilter === cat.id
                    ? 'bg-foreground text-background border-foreground shadow-sm'
                    : 'bg-background hover:bg-secondary border-border text-foreground'
                }`}
              >
                <Icon size={13} />
                <span>{t(cat.labelKey)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Timespan Filter */}
      <div className="shrink-0">
        <span className="ui-kicker text-muted-foreground block mb-2">
          {t('search.timespan_label')}
        </span>
        <div className="flex gap-1.5">
          {timespans.map((option) => (
            <button
              key={option.id}
              data-testid="search-timespan-chip"
              data-timespan={option.id}
              onClick={() => onTimespanChange(option.id)}
              className={`search-cmd-chip px-3 py-1 rounded-none transition-all border ${
                timespan === option.id
                  ? 'bg-foreground text-background border-foreground shadow-sm'
                  : 'bg-background hover:bg-secondary border-border text-foreground'
              }`}
            >
              {t(option.labelKey)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
