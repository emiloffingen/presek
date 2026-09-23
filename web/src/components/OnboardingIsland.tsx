import { localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRight, CheckCircle2, Sparkles, X } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $onboarding, updateProfile, updateOnboarding } from '../lib/store.ts';
import {
  buildSurfaceFollowSuggestions,
  completeOnboarding,
  dismissOnboarding,
  getOnboardingProgress,
  recordSuggestionDismiss,
  recordSuggestionFollow,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';
import { useClientTranslations } from '../i18n/clientTranslations';
import { common } from '../i18n/namespaces/common';
import { nav } from '../i18n/namespaces/nav';

export default function OnboardingIsland({ compact = false, lang = 'mk' }: { compact?: boolean, lang?: string }) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, common, nav);
  const profile = useStore($profile);
  const onboarding = useStore($onboarding);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const progress = useMemo(() => getOnboardingProgress(isMounted ? undefined : null as any, lang), [isMounted, profile, onboarding, lang]);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (!progress.shouldShow) {
      setVisible(false);
    }
  }, [progress.shouldShow]);

  const activeProfile = isMounted ? profile : null;
  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(activeProfile, 'onboarding', { topicLimit: compact ? 2 : 3, sourceLimit: compact ? 1 : 2, lang }),
    [activeProfile, compact, lang]
  );

  useEffect(() => {
    if (!compact || !visible) return;
    const result = recordSuggestionImpressions('onboarding', [
      ...recommendations.topics.map((item) => ({ kind: 'topic' as const, value: item.value })),
      ...recommendations.sources.map((item) => ({ kind: 'source' as const, value: item.value })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'onboarding',
        eventType: 'impression',
        suggestionKind: item.kind,
        value: item.value,
      }))
    );
  }, [compact, recommendations, visible]);

  if (!visible || !progress.shouldShow) {
    return null;
  }

  const close = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const next = dismissOnboarding();
      updateOnboarding(next);
      const tracked = recordSuggestionDismiss('onboarding');
      if (tracked.recorded) {
        sendSuggestionEvents([{ surface: 'onboarding', eventType: 'dismiss' }]);
      }
      setVisible(false);
    } catch (err) {
      console.error('Failed to dismiss onboarding:', err);
      setVisible(false);
    }
  };

  const markDone = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const next = completeOnboarding();
      updateOnboarding(next);
      setVisible(false);
    } catch (err) {
      console.error('Failed to complete onboarding:', err);
      setVisible(false);
    }
  };

  const quickFollow = (kind: 'topic' | 'source', value: string) => {
    const field = kind === 'source' ? 'followedSources' : 'followedTopics';
    const currentList = profile[field] || [];
    const newList = [...new Set([...currentList, value])].slice(0, 12);

    updateProfile({ [field]: newList });

    const tracked = recordSuggestionFollow('onboarding', kind, value);
    if (tracked.recorded) {
        sendSuggestionEvents([{ surface: 'onboarding', eventType: 'follow', suggestionKind: kind, value }]);
    }
  };

  return (
    <section className={`onboarding-card ${compact ? 'is-compact' : ''}`}>
      <div className="onboarding-head">
        <div>
          <p className="onboarding-kicker"><Sparkles size={14} /> {t('onboarding.kicker')}</p>
          <h2>{t('onboarding.title')}</h2>
        </div>
        <button type="button" className="onboarding-dismiss" onClick={close} aria-label={t('nav.close')}>
          <X size={14} />
        </button>
      </div>

      <p className="onboarding-copy">{t('onboarding.copy')}</p>

      <div className="onboarding-progress mt-4 mb-6">
        <div className="flex justify-between items-center text-[10px] font-black tracking-wider uppercase text-muted-foreground mb-1.5">
          <span>{t('onboarding.progress')}</span>
          <strong>{progress.doneCount}/{progress.total}</strong>
        </div>
        <div className="premium-progress-track">
          <div
            className="premium-progress-fill"
            style={{ width: `${(progress.doneCount / (progress.total || 1)) * 100}%` }}
          />
        </div>
      </div>

      <div className="onboarding-steps">
        {progress.steps.map((step: any) => (
          <div key={step.id} className={`onboarding-step ${step.done ? 'is-done' : ''}`}>
            <span className="onboarding-step-icon">{step.done ? <CheckCircle2 size={14} /> : <ArrowRight size={14} />}</span>
            <span>{step.label}</span>
          </div>
        ))}
      </div>

      {compact && (recommendations.topics.length > 0 || recommendations.sources.length > 0) && (
        <div className="onboarding-starters">
          <div>
            <p className="onboarding-starters-title">{t('onboarding.quick_start')}</p>
            <p className="onboarding-starters-copy">{t('onboarding.quick_start_copy')}</p>
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
        <a href={localePathForLang('/settings', locale)} className="onboarding-action">{t('onboarding.open_settings')}</a>
        <button type="button" className="onboarding-action secondary" onClick={markDone}>{t('onboarding.hide_guide')}</button>
      </div>
    </section>
  );
}
