import { LoaderCircle } from 'lucide-react';
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
        className="w-full bg-transparent py-2.5 sm:py-4 text-xl sm:text-2xl md:text-3xl font-serif font-black text-foreground outline-none placeholder:text-muted-foreground/40 border-b-2 border-transparent focus:border-foreground transition-colors search-cmd-input"
        autoComplete="off"
        spellCheck="false"
      />
      {isLoading && (
        <div className="absolute right-0 top-1/2 -translate-y-1/2">
          <LoaderCircle size={20} className="animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
