import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useTranslations } from '../i18n/utils';

const STORAGE_KEY = 'ui-concepts-onboarding-dismissed';

const STEPS = [
  { titleKey: 'onboarding_ui.step1_title', bodyKey: 'onboarding_ui.step1_body' },
  { titleKey: 'onboarding_ui.step2_title', bodyKey: 'onboarding_ui.step2_body' },
  { titleKey: 'onboarding_ui.step3_title', bodyKey: 'onboarding_ui.step3_body' },
] as const;

export default function UiConceptOnboarding({ lang = 'sr' }: { lang?: string }) {
  const t = useTranslations(lang as 'sr' | 'mk');
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const primaryBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(STORAGE_KEY) === '1') return;

    let shown = false;
    const show = () => {
      if (shown) return;
      shown = true;
      setVisible(true);
    };

    const onScroll = () => {
      if (window.scrollY > 180) show();
    };

    const timer = window.setTimeout(show, window.matchMedia('(max-width: 768px)').matches ? 8000 : 4000);
    window.addEventListener('scroll', onScroll, { passive: true });
    if (window.scrollY > 180) show();

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    primaryBtnRef.current?.focus();

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
        return;
      }
      if (event.key !== 'Tab' || focusable.length === 0) return;
      if (event.shiftKey && event.target === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && event.target === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [visible, step]);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  };

  if (!visible) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div
      ref={dialogRef}
      className="ui-concept-onboarding"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ui-concept-title"
      aria-describedby="ui-concept-body"
    >
      <button type="button" className="ui-concept-close" onClick={dismiss} aria-label={t('nav.close')}>
        <X size={16} />
      </button>
      <p className="ui-concept-kicker">{t('onboarding_ui.kicker')} · {step + 1}/{STEPS.length}</p>
      <h2 id="ui-concept-title" className="ui-concept-title">{t(current.titleKey)}</h2>
      <p id="ui-concept-body" className="ui-concept-body">{t(current.bodyKey)}</p>
      <div className="ui-concept-actions">
        {step > 0 && (
          <button type="button" className="ui-concept-secondary" onClick={() => setStep((s) => s - 1)}>
            {t('onboarding_ui.back')}
          </button>
        )}
        <button
          ref={primaryBtnRef}
          type="button"
          className="ui-concept-primary"
          onClick={() => (isLast ? dismiss() : setStep((s) => s + 1))}
        >
          {isLast ? t('onboarding_ui.done') : t('onboarding_ui.next')}
        </button>
      </div>
    </div>
  );
}
