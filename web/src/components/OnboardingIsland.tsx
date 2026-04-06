import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRight, CheckCircle2, Sparkles, X } from 'lucide-react';
import {
  buildFollowRecommendations,
  completeOnboarding,
  dismissOnboarding,
  getOnboardingProgress,
  loadReaderProfile,
  toggleFollowedValue,
} from '../lib/personalization.js';

export default function OnboardingIsland({ compact = false }: { compact?: boolean }) {
  const [progress, setProgress] = useState(() => getOnboardingProgress());
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    setProgress(getOnboardingProgress());
    setProfile(loadReaderProfile());
  }, []);

  const recommendations = useMemo(() => buildFollowRecommendations(profile, compact ? 2 : 3), [profile, compact]);

  if (!progress.shouldShow) {
    return null;
  }

  const close = () => {
    const next = dismissOnboarding();
    setProgress((current) => ({ ...current, dismissed: next.dismissed, shouldShow: false }));
  };

  const markDone = () => {
    completeOnboarding();
    setProgress((current) => ({ ...current, completed: true, shouldShow: false }));
  };

  const quickFollow = (kind: 'topic' | 'source', value: string) => {
    const result = toggleFollowedValue(kind, value);
    setProfile(result.profile);
    setProgress(getOnboardingProgress());
  };

  return (
    <section className={`onboarding-card ${compact ? 'is-compact' : ''}`}>
      <div className="onboarding-head">
        <div>
          <p className="onboarding-kicker"><Sparkles size={14} /> Започнете со Пресек</p>
          <h2>Поставете го вашиот персонализиран тек</h2>
        </div>
        <button type="button" className="onboarding-dismiss" onClick={close} aria-label="Затвори">
          <X size={14} />
        </button>
      </div>

      <p className="onboarding-copy">
        Следете неколку теми и извори, па вклучете достава. Така `За Вас`, брифинзите и известувањата ќе почнат да работат како личен сервис, а не само како општа насловна.
      </p>

      <div className="onboarding-progress">
        <strong>{progress.doneCount}/{progress.total}</strong>
        <span>чекори завршени</span>
      </div>

      <div className="onboarding-steps">
        {progress.steps.map((step) => (
          <div key={step.id} className={`onboarding-step ${step.done ? 'is-done' : ''}`}>
            <span className="onboarding-step-icon">{step.done ? <CheckCircle2 size={14} /> : <ArrowRight size={14} />}</span>
            <span>{step.label}</span>
          </div>
        ))}
      </div>

      {compact && (recommendations.topics.length > 0 || recommendations.sources.length > 0) && (
        <div className="onboarding-starters">
          <div>
            <p className="onboarding-starters-title">Почнете со неколку брзи следења</p>
            <p className="onboarding-starters-copy">Изберете 1 до 2 сигнали за `За Вас`, известувањата и неделниот преглед да станат побрзо корисни.</p>
          </div>

          {recommendations.topics.length > 0 && (
            <div className="onboarding-chip-row">
              {recommendations.topics.map((item) => (
                <button
                  key={`topic:${item.value}`}
                  type="button"
                  className="onboarding-chip"
                  onClick={() => quickFollow('topic', item.value)}
                >
                  <span>{item.value}</span>
                  <small>{item.reason}</small>
                </button>
              ))}
            </div>
          )}

          {recommendations.sources.length > 0 && (
            <div className="onboarding-chip-row">
              {recommendations.sources.map((item) => (
                <button
                  key={`source:${item.value}`}
                  type="button"
                  className="onboarding-chip"
                  onClick={() => quickFollow('source', item.value)}
                >
                  <span>{item.value}</span>
                  <small>{item.reason}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="onboarding-actions">
        <a href="/settings" className="onboarding-action">Отвори поставки</a>
        <button type="button" className="onboarding-action secondary" onClick={markDone}>Скриј го водичот</button>
      </div>
    </section>
  );
}
