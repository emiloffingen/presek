import React, { useEffect, useState } from 'react';
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

  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    setVisible(localStorage.getItem(STORAGE_KEY) !== '1');
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  };

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div className="ui-concept-onboarding" role="dialog" aria-label={t('onboarding_ui.label')}>
      <button type="button" className="ui-concept-close" onClick={dismiss} aria-label={t('nav.close')}>
        <X size={16} />
      </button>
      <p className="ui-concept-kicker">{t('onboarding_ui.kicker')} · {step + 1}/{STEPS.length}</p>
      <h2 className="ui-concept-title">{t(current.titleKey)}</h2>
      <p className="ui-concept-body">{t(current.bodyKey)}</p>
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
    </div>
  );
}
