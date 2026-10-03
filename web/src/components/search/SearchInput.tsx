import { LoaderCircle, X } from 'lucide-react';
import type React from 'react';

type SearchInputProps = {
  query: string;
  onChange: (value: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  isLoading: boolean;
  placeholder: string;
};

export function SearchInput({
  query,
  onChange,
  inputRef,
  isLoading,
  placeholder,
}: SearchInputProps) {
  return (
    <div className="flex-1 relative">
      <input
        ref={inputRef}
        type="text"
        data-testid="search-input"
        value={query}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-full bg-transparent pr-12 py-2.5 sm:py-4 text-xl sm:text-2xl md:text-3xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 border-b-2 border-transparent focus:border-foreground transition-colors search-cmd-input"
        autoComplete="off"
        spellCheck="false"
      />
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2">
        {isLoading && (
          <LoaderCircle size={18} className="animate-spin text-muted-foreground" />
        )}
        {query && (
          <button
            onClick={() => {
              onChange('');
              inputRef.current?.focus();
            }}
            className="p-1 hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors rounded-none"
            title="Clear search"
            type="button"
          >
            <X size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
