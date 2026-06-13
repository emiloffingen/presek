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

type TabId = 'pregled' | 'profil' | 'dostava' | 'sinhronizacija' | 'vodic';

function activateSettingsTab(tab: TabId) {
  if (typeof document === 'undefined') return;
  const button = document.querySelector(`.settings-tab-btn[data-tab="${tab}"]`);
  button?.dispatchEvent(new Event('click', { bubbles: true }));
  window.history.replaceState(null, '', `#${tab}`);
}

export default function SettingsOverviewIsland({ lang = 'sr' }: { lang?: string }) {
  const profile = useStore($profile);
  const syncToken = useStore($syncToken);
  const deliveryPrefs = useStore($deliveryPrefs);
  const isMK = lang === 'mk';

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
        label: isMK ? 'Профил & теми' : 'Profil & teme',
        value: `${followedTopics.length + followedSources.length}`,
        note: isMK ? 'активни сигнали' : 'aktivnih signala',
        hint: isMK ? 'Уредете што следите' : 'Uredite šta pratite',
      },
      {
        id: 'dostava' as TabId,
        icon: Mail,
        label: isMK ? 'Jutarnje izdanje' : 'Jutarnje izdanje',
        value: deliveryPrefs.morningBriefing ? (isMK ? 'Push' : 'Push') : (isMK ? 'Искл.' : 'Iskl.'),
        note: isMK ? 'локална достава' : 'lokalna dostava',
        hint: isMK ? 'E-pošta + push + ntfy' : 'E-pošta + push + ntfy',
      },
      {
        id: 'sinhronizacija' as TabId,
        icon: KeyRound,
        label: isMK ? 'Синхронизација' : 'Sinhronizacija',
        value: syncToken ? (isMK ? 'Активна' : 'Aktivna') : (isMK ? 'Локално' : 'Lokalno'),
        note: isMK ? 'дигитален пасош' : 'digitalni pasoš',
        hint: syncToken
          ? (isMK ? 'Профилот е поврзан' : 'Profil je povezan')
          : (isMK ? 'Поврзете уреди' : 'Povežite uređaje'),
      },
    ],
    [deliveryPrefs.morningBriefing, followedSources.length, followedTopics.length, isMK, syncToken],
  );

  return (
    <div className="settings-overview">
      <section className="settings-overview-hero">
        <div>
          <span className="settings-overview-kicker">
            <Gauge size={15} /> {isMK ? 'Преглед' : 'Pregled'}
          </span>
          <h2>{isMK ? 'Едно место за профил, достава и синхронизација' : 'Jedno mesto za profil, dostavu i sinhronizaciju'}</h2>
          <p>
            {isMK
              ? 'Проверете колку е силен вашиот сигнал, закажете утринско издание и отворете персонализиран пресек.'
              : 'Proverite koliko je jak vaš signal, zakažite jutarnje izdanje i otvorite personalizovan presek.'}
          </p>
        </div>
        <div className="settings-overview-meter" aria-label={isMK ? 'Сила на сигналот' : 'Jačina signala'}>
          <div className="settings-overview-meter-head">
            <span>{isMK ? 'Сигнал на профилот' : 'Signal profila'}</span>
            <strong>{signalStrength}%</strong>
          </div>
          <div className="settings-overview-meter-bar">
            <span style={{ width: `${signalStrength}%` }} />
          </div>
          <p>
            {hasSignals
              ? isMK
                ? `${followedTopics.length} теми · ${followedSources.length} извори · ${recentCount} неодамнешни`
                : `${followedTopics.length} tema · ${followedSources.length} izvora · ${recentCount} nedavnih`
              : isMK
                ? 'Додајте теми или извори за посилен личен пресек.'
                : 'Dodajte teme ili izvore za jači lični presek.'}
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
        <a href={localePathForLang('/for-you', isMK ? 'mk' : 'sr')} className="settings-overview-link">
          <Compass size={16} />
          <span>
            <strong>{isMK ? 'Отвори За Вас' : 'Otvori Za Vas'}</strong>
            <small>{isMK ? 'Личен пресек според вашите сигнали' : 'Lični presek prema vašim signalima'}</small>
          </span>
          <ArrowUpRight size={14} />
        </a>
        <a href={localePathForLang('/briefing', isMK ? 'mk' : 'sr')} className="settings-overview-link">
          <Newspaper size={16} />
          <span>
            <strong>{isMK ? 'Дневен брифинг' : 'Dnevni brifing'}</strong>
            <small>{isMK ? 'Уредничко издание за денот' : 'Uredničko izdanje za danas'}</small>
          </span>
          <ArrowUpRight size={14} />
        </a>
        <button type="button" className="settings-overview-link" onClick={() => activateSettingsTab('dostava')}>
          <BellRing size={16} />
          <span>
            <strong>{isMK ? 'Подеси достава' : 'Podesi dostavu'}</strong>
            <small>{isMK ? 'E-pošta, push и ntfy на едно место' : 'E-pošta, push i ntfy na jednom mestu'}</small>
          </span>
          <ArrowUpRight size={14} />
        </button>
        <button type="button" className="settings-overview-link" onClick={() => activateSettingsTab('vodic')}>
          <Sparkles size={16} />
          <span>
            <strong>{isMK ? 'Водич за почеток' : 'Vodič za početak'}</strong>
            <small>{isMK ? '4 чекори до подобар личен пресек' : '4 koraka do boljeg ličnog preseka'}</small>
          </span>
          <ArrowUpRight size={14} />
        </button>
      </div>

      <section className="settings-overview-email premium-card">
        <div className="settings-overview-email-head">
          <Radio size={16} />
          <div>
            <h3>{isMK ? 'Утринско издание на e-pošta' : 'Jutarnje izdanje na e-poštu'}</h3>
            <p>
              {isMK
                ? 'Истиот уреднички брифинг што го читате на страницата — секое утро во 08:00.'
                : 'Isti urednički brifing koji čitate na stranici — svako jutro u 08:00.'}
            </p>
          </div>
        </div>
        <MorningEmailSignup lang={isMK ? 'mk' : 'sr'} variant="settings" />
      </section>
    </div>
  );
}
