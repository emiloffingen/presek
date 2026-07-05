import { Mic } from 'lucide-react';
import type { TFunction } from './types';

type VoiceSearchOverlayProps = {
  isListening: boolean;
  onCancel: () => void;
  t: TFunction;
};

export function VoiceSearchOverlay({ isListening, onCancel, t }: VoiceSearchOverlayProps) {
  if (!isListening) return null;

  return (
    <div className="absolute inset-0 bg-background/95 backdrop-blur-md z-[10001] flex flex-col items-center justify-center gap-6 animate-in fade-in duration-300">
      <div className="w-20 h-20 bg-secondary rounded-full flex items-center justify-center text-muted-foreground animate-pulse border border-border shadow-lg">
        <Mic size={36} />
      </div>

      <div className="flex items-center gap-1.5 h-10 justify-center">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="w-1.5 bg-foreground rounded-full animate-bounce"
            style={{
              height: '24px',
              animationDelay: `${i * 0.15}s`,
              animationDuration: '0.8s'
            }}
          />
        ))}
      </div>

      <p className="font-serif font-black text-xl text-center">{t('search.listening')}</p>

      <button
        onClick={onCancel}
        className="search-cmd-cta px-6 py-2.5 bg-secondary hover:bg-secondary-foreground/10 border border-border rounded-none transition-all"
      >
        {t('search.cancel')}
      </button>
    </div>
  );
}
