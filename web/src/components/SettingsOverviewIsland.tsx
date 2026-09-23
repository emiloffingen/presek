import React, { useMemo } from 'react';
import { useStore } from '@nanostores/react';
import {
  ArrowUpRight,
  BellRing,
  Compass,
  Gauge,
  KeyRound,
  Mail,
  Newspaper,
  Radio,
  Sparkles,
  UserCircle2,
} from 'lucide-react';
import { $deliveryPrefs, $profile, $syncToken } from '../lib/store.ts';
import { hasPersonalizationSignal } from '../lib/personalization.js';
import { localePathForLang } from '../lib/localePaths';
import MorningEmailSignup from './MorningEmailSignup.tsx';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';

type TabId = 'pregled' | 'profil' | 'dostava' | 'sinhronizacija' | 'vodic';

function activateSettingsTab(tab: TabId) {
  if (typeof window === 'undefined') return;
  window.location.hash = tab;
}

export default function SettingsOverviewIsland({ lang = 'mk' }: { lang?: string }) {
  const profile = useStore($profile);
  const syncToken = useStore($syncToken);
  const deliveryPrefs = useStore($deliveryPrefs);
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useClientTranslations(locale, settings);

  const followedTopics = profile?.followedTopics || [];
  const followedSources = profile?.followedSources || [];
  const recentCount = profile?.recentClusters?.length || 0;
  const signalStrength = Math.min(
    100,
    Math.round(followedTopics.length * 12 + followedSources.length * 16 + recentCount * 2),
  );
  const hasSignals = hasPersonalizationSignal(profile);

  const cards = useMemo(
    () => [
      {
        id: 'profil' as TabId,
        icon: UserCircle2,
        label: t('settings.overview_card_profile'),
        value: `${followedTopics.length + followedSources.length}`,
        note: t('settings.overview_card_profile_note'),
        hint: t('settings.overview_card_profile_hint'),
      },
      {
        id: 'dostava' as TabId,
        icon: Mail,
        label: t('settings.overview_morning_label'),
        value: deliveryPrefs.morningBriefing
          ? t('settings.overview_delivery_enabled')
          : t('settings.overview_delivery_disabled'),
        note: t('settings.overview_delivery_note'),
        hint: t('settings.overview_delivery_hint'),
      },
      {
        id: 'sinhronizacija' as TabId,
        icon: KeyRound,
        label: t('settings.overview_card_sync'),
        value: syncToken
          ? t('settings.overview_card_sync_note_active')
          : t('settings.overview_card_sync_note_local'),
        note: t('settings.overview_card_sync_value_local'),
        hint: syncToken
          ? t('settings.overview_card_sync_hint_active')
          : t('settings.overview_card_sync_hint_local'),
      },
    ],
    [deliveryPrefs.morningBriefing, followedSources.length, followedTopics.length, syncToken, t],
  );

  return (
    <div className="settings-overview">
      <section className="settings-overview-hero">
        <div>
          <span className="settings-overview-kicker">
            <Gauge size={15} /> {t('settings.overview_kicker')}
          </span>
          <h2>{t('settings.overview_title')}</h2>
          <p>{t('settings.overview_desc')}</p>
        </div>
        <div className="settings-overview-meter" aria-label={t('settings.overview_meter_label')}>
          <div className="settings-overview-meter-head">
            <span>{t('settings.overview_meter_head')}</span>
            <strong>{signalStrength}%</strong>
          </div>
          <div className="settings-overview-meter-bar">
            <span style={{ width: `${signalStrength}%` }} />
          </div>
          <p>
            {hasSignals
              ? t('settings.overview_stats_active', {
                  topics: followedTopics.length,
                  sources: followedSources.length,
                  recent: recentCount,
                })
              : t('settings.overview_stats_empty')}
          </p>
        </div>
      </section>

      <div className="settings-overview-grid">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <button
              key={card.id}
              type="button"
              className="settings-overview-card"
              onClick={() => activateSettingsTab(card.id)}
            >
              <span className="settings-overview-card-icon">
                <Icon size={16} />
              </span>
              <span className="settings-overview-card-label">{card.label}</span>
              <strong>{card.value}</strong>
              <span className="settings-overview-card-note">{card.note}</span>
              <span className="settings-overview-card-hint">{card.hint}</span>
            </button>
          );
        })}
      </div>

      <div className="settings-overview-links">
        <a href={localePathForLang('/for-you', locale)} className="settings-overview-link">
          <Compass size={16} />
          <span>
            <strong>{t('settings.overview_link_foryou')}</strong>
            <small>{t('settings.overview_link_foryou_desc')}</small>
          </span>
          <ArrowUpRight size={14} />
        </a>
        <a href={localePathForLang('/briefing', locale)} className="settings-overview-link">
          <Newspaper size={16} />
          <span>
            <strong>{t('settings.overview_link_briefing')}</strong>
            <small>{t('settings.overview_link_briefing_desc')}</small>
          </span>
          <ArrowUpRight size={14} />
        </a>
        <button type="button" className="settings-overview-link" onClick={() => activateSettingsTab('dostava')}>
          <BellRing size={16} />
          <span>
            <strong>{t('settings.overview_link_delivery')}</strong>
            <small>{t('settings.overview_delivery_link_note')}</small>
          </span>
          <ArrowUpRight size={14} />
        </button>
        <button type="button" className="settings-overview-link" onClick={() => activateSettingsTab('vodic')}>
          <Sparkles size={16} />
          <span>
            <strong>{t('settings.overview_link_guide')}</strong>
            <small>{t('settings.overview_link_guide_desc')}</small>
          </span>
          <ArrowUpRight size={14} />
        </button>
      </div>

      <section className="settings-overview-email premium-card">
        <div className="settings-overview-email-head">
          <Radio size={16} />
          <div>
            <h3>{t('settings.overview_morning_email_title')}</h3>
            <p>{t('settings.overview_morning_email_desc')}</p>
          </div>
        </div>
        <MorningEmailSignup lang={locale} variant="settings" />
      </section>
    </div>
  );
}
