import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

const CONSENT_KEY = 'presek_cookie_consent';
const DISMISS_COOLDOWN_MS = 1000 * 60 * 60 * 24 * 3;

type ConsentState =
  | 'accepted'
  | {
      status: 'accepted' | 'dismissed';
      ts: number;
    };

function readConsentState(): boolean {
  if (typeof window === 'undefined') return true;
  const raw = localStorage.getItem(CONSENT_KEY);
  if (!raw) return false;
  
  if (raw === 'accepted') return true;

  try {
    const parsed = JSON.parse(raw);
    return parsed?.status === 'accepted';
  } catch {
    return false;
  }
}

function writeConsentState(status: 'accepted' | 'dismissed') {
  if (typeof window === 'undefined') return;
  if (status === 'accepted') {
    localStorage.setItem(CONSENT_KEY, 'accepted');
  } else {
    localStorage.setItem(
      CONSENT_KEY,
      JSON.stringify({
        status,
        ts: Date.now(),
      })
    );
  }
}

export const ConsentBanner: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (readConsentState()) {
      return;
    }

    // Check for dismissed cooldown
    if (typeof window !== 'undefined') {
      const raw = localStorage.getItem(CONSENT_KEY);
      if (raw && raw !== 'accepted') {
        try {
          const parsed = JSON.parse(raw);
          if (parsed.status === 'dismissed' && Date.now() - parsed.ts < DISMISS_COOLDOWN_MS) {
            return;
          }
        } catch {}
      }
    }

    // Show after a short delay to not block initial render.
    const timer = setTimeout(() => setVisible(true), 1000);
    return () => clearTimeout(timer);
  }, []);

  const accept = () => {
    writeConsentState('accepted');
    setVisible(false);
  };

  const dismiss = () => {
    writeConsentState('dismissed');
    setVisible(false);
  };

  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (visible) {
      document.body.classList.add('has-consent-banner');
    } else {
      document.body.classList.remove('has-consent-banner');
    }
    return () => document.body.classList.remove('has-consent-banner');
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[100] px-2 pb-2 md:p-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="mx-auto max-w-5xl rounded-2xl border border-border bg-background/94 px-2.5 py-1.5 shadow-[0_-8px_30px_rgba(17,24,39,0.08)] backdrop-blur-md md:px-5 md:py-3.5">
        <div className="flex items-center gap-2 md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-2">
              <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.14em] text-foreground">Kolacinja i privatnost</h3>
              <span className="hidden md:inline text-[11px] text-muted-foreground">•</span>
              <span className="hidden md:inline text-xs text-muted-foreground">Kratko izvestuvanje</span>
            </div>
            <p className="text-[10px] text-secondary-foreground leading-snug md:hidden">
              Personalizacija i analiza.
              {' '}
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="underline underline-offset-2 hover:text-nyt-accent"
              >
                {expanded ? 'Skrij detali' : 'Povece'}
              </button>
            </p>
            {expanded && (
              <p className="mt-1 text-[11px] text-secondary-foreground leading-snug md:hidden">
                Koristime kolacinja za personalizacija, oglasi i analiza na soobracajot.
                {' '}
                <a href="/privacy" className="underline underline-offset-2 hover:text-nyt-accent">Politika za privatnost</a>.
              </p>
            )}
            <p className="hidden text-[13px] text-secondary-foreground leading-relaxed md:block">
              Koristime kolacinja za personalizacija, oglasi i analiza na soobracajot.
              {' '}
              <a href="/privacy" className="underline underline-offset-2 hover:text-nyt-accent">Politika za privatnost</a>.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1 self-auto">
            <button
              onClick={dismiss}
              aria-label="Zatvori"
              className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-border/80 text-muted-foreground transition-colors hover:text-foreground md:h-9 md:w-9"
            >
              <X size={12} />
            </button>
            <button
              onClick={accept}
              className="rounded-full bg-foreground px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.14em] text-background transition-colors hover:bg-nyt-accent hover:text-white md:px-4 md:py-2 md:text-[11px]"
            >
              Prifacam
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConsentBanner;
