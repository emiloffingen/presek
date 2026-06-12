import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useTranslations } from '../i18n/utils';
import { localePathForLang } from '../lib/localePaths';

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
  const [leadHref, setLeadHref] = useState<string>('');
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(STORAGE_KEY) === '1') return;
    setLeadHref(document.querySelector<HTMLAnchorElement>('.lead-copy a[data-testid="cluster-link"]')?.href || '');

    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    let shown = false;
    const show = () => {
      if (shown) return;
      if (document.body.classList.contains('has-consent-banner')) return;
      shown = true;
      setVisible(true);
    };

    const scrollThreshold = isMobile ? 320 : 220;
    const onScroll = () => {
      if (window.scrollY > scrollThreshold) show();
    };

    const timer = window.setTimeout(show, isMobile ? 18000 : 8000);
    window.addEventListener('scroll', onScroll, { passive: true });
    if (window.scrollY > scrollThreshold) show();

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
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

  useEffect(() => {
    if (!visible) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [visible, step]);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  };

  const openAnalysis = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
    window.location.assign(localePathForLang('/pregled', lang as 'sr' | 'mk'));
  };

  if (!visible) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div
      ref={dialogRef}
      className="ui-concept-onboarding"
      role="note"
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
  );
}
