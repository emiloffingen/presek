import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

export const ConsentBanner: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem('presek_cookie_consent');
    if (!consent) {
      // Show after a short delay to not block initial render
      const timer = setTimeout(() => setVisible(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const accept = () => {
    localStorage.setItem('presek_cookie_consent', 'accepted');
    setVisible(false);
  };

  const dismiss = () => {
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[100] p-3 md:p-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="max-w-5xl mx-auto border border-border bg-background/96 backdrop-blur-md shadow-[0_-8px_30px_rgba(17,24,39,0.08)] rounded-2xl px-4 py-3 md:px-5 md:py-3.5">
        <div className="flex items-start gap-3 md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.14em] text-foreground">Колачиња и приватност</h3>
              <span className="hidden md:inline text-[11px] text-muted-foreground">•</span>
              <span className="hidden md:inline text-xs text-muted-foreground">Кратко известување</span>
            </div>
            <p className="text-xs md:text-[13px] text-secondary-foreground leading-relaxed md:hidden">
              Користиме колачиња за персонализација и анализа.
              {' '}
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="underline underline-offset-2 hover:text-nyt-accent"
              >
                {expanded ? 'Скриј детали' : 'Повеќе'}
              </button>
            </p>
            {expanded && (
              <p className="mt-1 text-[12px] text-secondary-foreground leading-relaxed md:hidden">
                Користиме колачиња за персонализација, огласи и анализа на сообраќајот.
                {' '}
                <a href="/privacy" className="underline underline-offset-2 hover:text-nyt-accent">Политика за приватност</a>.
              </p>
            )}
            <p className="hidden text-[13px] text-secondary-foreground leading-relaxed md:block">
              Користиме колачиња за персонализација, огласи и анализа на сообраќајот.
              {' '}
              <a href="/privacy" className="underline underline-offset-2 hover:text-nyt-accent">Политика за приватност</a>.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 self-end md:self-auto">
            <button
              onClick={dismiss}
              aria-label="Затвори"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:text-foreground md:h-9 md:w-9"
            >
              <X size={14} />
            </button>
            <button
              onClick={accept}
              className="px-3.5 py-2 bg-foreground text-background font-sans text-[10px] font-black uppercase tracking-[0.14em] hover:bg-nyt-accent hover:text-white transition-colors rounded-full md:px-4 md:text-[11px]"
            >
              Прифаќам
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConsentBanner;
