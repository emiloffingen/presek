import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useTranslations } from '../i18n/utils';
import { localePathForLang } from '../lib/localePaths';

const STORAGE_KEY = 'ui-concepts-onboarding-dismissed';
const FIRST_SESSION_KEY = 'homepage-visit-count';

const STEPS = [
  { titleKey: 'onboarding_ui.step1_title', bodyKey: 'onboarding_ui.step1_body' },
  { titleKey: 'onboarding_ui.step2_title', bodyKey: 'onboarding_ui.step2_body' },
  { titleKey: 'onboarding_ui.step3_title', bodyKey: 'onboarding_ui.step3_body' },
] as const;

export default function UiConceptOnboarding({ lang = 'sr' }: { lang?: string }) {
  const t = useTranslations(lang as 'sr' | 'mk');
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [leadHref, setLeadHref] = useState<string>('');
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(STORAGE_KEY) === '1') return;
    if (!document.querySelector('[data-home-session-root]')) return;

    const visits = Number(localStorage.getItem(FIRST_SESSION_KEY) || '0');
    if (visits > 4) return;

    setLeadHref(document.querySelector<HTMLAnchorElement>('.lead-copy a[data-testid="cluster-link"]')?.href || '');

    let shown = false;
    let consentObserver: MutationObserver | null = null;

    const tryShow = () => {
      if (shown) return true;
      if (document.body.classList.contains('has-consent-banner')) return false;
      shown = true;
      consentObserver?.disconnect();
      consentObserver = null;
      setVisible(true);
      return true;
    };

    const show = () => {
      if (tryShow()) return;
      if (!consentObserver) {
        consentObserver = new MutationObserver(() => {
          tryShow();
        });
        consentObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
      }
    };

    const isFirstVisit = visits <= 1;
    const feed = document.getElementById('home-unified-feed');

    if (isFirstVisit) {
      if (!feed) return;

      const observer = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting && entry.intersectionRatio >= 0.12) {
          show();
          observer.disconnect();
        }
      }, { threshold: [0, 0.12, 0.25], rootMargin: '0px 0px -18% 0px' });

      observer.observe(feed);

      const onScroll = () => {
        if (window.scrollY > 520) show();
      };
      window.addEventListener('scroll', onScroll, { passive: true });

      return () => {
        observer.disconnect();
        window.removeEventListener('scroll', onScroll);
        consentObserver?.disconnect();
      };
    }

    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    const scrollThreshold = isMobile ? 220 : 160;
    const onScroll = () => {
      if (window.scrollY > scrollThreshold) show();
    };

    const timer = window.setTimeout(show, isMobile ? 4500 : 3500);
    window.addEventListener('scroll', onScroll, { passive: true });
    if (window.scrollY > scrollThreshold) show();

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
      consentObserver?.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!visible) {
      document.body.classList.remove('has-ui-onboarding');
      return;
    }
    document.body.classList.add('has-ui-onboarding');
    return () => document.body.classList.remove('has-ui-onboarding');
  }, [visible]);

  const dismiss = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  }, []);

  const openAnalysis = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
    window.location.assign(localePathForLang('/pregled', lang as 'sr' | 'mk'));
  };

  useEffect(() => {
    if (!visible) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
        return;
      }

      if (event.key !== 'Tab' || !dialogRef.current) return;

      const focusables = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((node) => !node.hasAttribute('disabled') && node.offsetParent !== null);

      if (focusables.length === 0) return;

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [visible, step, dismiss]);

  if (!visible) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <>
      <button
        type="button"
        className="ui-concept-backdrop"
        aria-label={t('nav.close')}
        onClick={dismiss}
      />
      <div
        ref={dialogRef}
        className="ui-concept-onboarding"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ui-concept-title"
        aria-describedby="ui-concept-body"
      >
        <button
          ref={closeButtonRef}
          type="button"
          className="ui-concept-close"
          onClick={dismiss}
          aria-label={t('nav.close')}
        >
          <X size={16} />
        </button>
        <p className="ui-concept-kicker" aria-live="polite">
          {t('onboarding_ui.kicker')} · {step + 1}/{STEPS.length}
        </p>
        <h2 id="ui-concept-title" className="ui-concept-title">{t(current.titleKey)}</h2>
        <p id="ui-concept-body" className="ui-concept-body">{t(current.bodyKey)}</p>
        <div className="ui-concept-actions">
          {step > 0 && (
            <button type="button" className="ui-concept-secondary" onClick={() => setStep((s) => s - 1)}>
              {t('onboarding_ui.back')}
            </button>
          )}
          <button
            type="button"
            className="ui-concept-primary"
            onClick={() => (isLast ? dismiss() : setStep((s) => s + 1))}
          >
            {isLast ? t('onboarding_ui.done') : t('onboarding_ui.next')}
          </button>
        </div>
        <div className="ui-concept-shortcuts">
          {leadHref && (
            <a href={leadHref} className="ui-concept-link" onClick={dismiss}>
              {lang === 'mk' ? 'Отвори главна приказна' : 'Otvori glavnu priču'}
            </a>
          )}
          <button type="button" className="ui-concept-link" onClick={openAnalysis}>
            {lang === 'mk' ? 'Види како се разликуваат извори' : 'Vidi kako se razlikuju izvori'}
          </button>
        </div>
      </div>
    </>
  );
}
