import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { getLangFromUrl, useTranslations } from '../i18n/utils';

const CONSENT_KEY = 'presek_cookie_consent';
const DISMISS_COOLDOWN_MS = 1000 * 60 * 60 * 24 * 3;

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
  const [lang] = useState<'sr' | 'mk'>(() => {
    if (typeof window === 'undefined') return 'sr';
    return getLangFromUrl(new URL(window.location.href)) as 'sr' | 'mk';
  });

  const t = useTranslations(lang);
  const l = (path: string) => lang === 'sr' ? path : `/mk${path}`;

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
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('consent', 'update', {
        'ad_storage': 'granted',
        'ad_user_data': 'granted',
        'ad_personalization': 'granted',
        'analytics_storage': 'granted'
      });
    }
    setVisible(false);
  };

  const dismiss = () => {
    writeConsentState('dismissed');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] isolate px-2 pb-2 md:p-4 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:duration-300"
      style={{ contain: 'layout paint style' }}
    >
      <div className="pointer-events-auto mx-auto max-w-5xl rounded-lg border border-border bg-popover/95 px-3 py-2 text-popover-foreground shadow-[0_-10px_28px_rgba(17,24,39,0.10)] backdrop-blur-xl md:px-5 md:py-3">
        <div className="flex items-center gap-3 md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-2">
              <h3 className="font-sans text-[11px] font-black uppercase tracking-[0.12em] text-foreground">{t('cookies.title')}</h3>
              <span className="hidden md:inline text-[11px] text-muted-foreground">•</span>
              <span className="hidden md:inline text-xs text-muted-foreground">{t('cookies.kicker')}</span>
            </div>
            <p className="text-[10px] text-secondary-foreground leading-snug md:hidden">
              {t('cookies.brief')}
              {' '}
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="underline underline-offset-2 hover:text-nyt-accent"
              >
                {expanded ? t('cookies.hide') : t('cookies.more')}
              </button>
            </p>
            {expanded && (
              <p className="mt-1 text-[11px] text-secondary-foreground leading-snug md:hidden">
                {t('cookies.details')}
                {' '}
                <a href={l('/privacy')} className="underline underline-offset-2 hover:text-nyt-accent">{t('nav.privacy')}</a>.
              </p>
            )}
            <p className="hidden text-[13px] text-secondary-foreground leading-relaxed md:block">
              {t('cookies.details')}
              {' '}
              <a href={l('/privacy')} className="underline underline-offset-2 hover:text-nyt-accent">{t('nav.privacy')}</a>.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 self-auto">
            <button
              onClick={dismiss}
              aria-label={t('cookies.dismiss')}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/80 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground md:h-9 md:w-9"
            >
              <X size={12} />
            </button>
            <button
              onClick={accept}
              className="rounded-md bg-foreground px-3 py-1.5 text-[9px] font-black uppercase tracking-[0.12em] text-background transition-colors hover:bg-nyt-accent hover:text-white md:px-4 md:py-2 md:text-[11px]"
            >
              {t('cookies.accept')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConsentBanner;
