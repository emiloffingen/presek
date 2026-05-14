import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRight, CheckCircle2, Sparkles, X } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $onboarding, updateProfile, updateOnboarding, getStoredOnboardingProgress } from '../lib/store.ts';
import {
  buildSurfaceFollowSuggestions,
  completeOnboarding,
  dismissOnboarding,
  recordSuggestionDismiss,
  recordSuggestionFollow,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';

export default function OnboardingIsland({ compact = false }: { compact?: boolean }) {
  const profile = useStore($profile);
  const onboarding = useStore($onboarding);
  const progress = useMemo(() => getStoredOnboardingProgress(), [profile, onboarding]);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (!progress.shouldShow) {
      setVisible(false);
    }
  }, [progress.shouldShow]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'onboarding', { topicLimit: compact ? 2 : 3, sourceLimit: compact ? 1 : 2 }),
    [profile, compact]
  );

  useEffect(() => {
    if (!compact || !visible) return;
    const result = recordSuggestionImpressions('onboarding', [
      ...recommendations.topics.map((item) => ({ kind: 'topic', value: item.value })),
      ...recommendations.sources.map((item) => ({ kind: 'source', value: item.value })),
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
          <p className="onboarding-kicker"><Sparkles size={14} /> Početno podešavanje</p>
          <h2>Postavite šta želite da pratite</h2>
        </div>
        <button type="button" className="onboarding-dismiss" onClick={close} aria-label="Zatvori">
          <X size={14} />
        </button>
      </div>

      <p className="onboarding-copy">
        Izaberite nekoliko tema ili izvora da biste personalizovali vaš sadržaj. Ovi signali pomažu modulu „Za Vas“, dnevni brifing i izveštaji da budu precizniji.
      </p>

      <div className="onboarding-progress">
        <strong>{progress.doneCount}/{progress.total}</strong>
        <span> koraka završeno</span>
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
            <p className="onboarding-starters-title">Brzi početak</p>
            <p className="onboarding-starters-copy">Izaberite 1 do 2 signala za prvi personalizovani pregled.</p>
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
        <a href="/settings" className="onboarding-action">Otvori podešavanja</a>
        <button type="button" className="onboarding-action secondary" onClick={markDone}>Sakrij vodič</button>
      </div>
    </section>
  );
}
