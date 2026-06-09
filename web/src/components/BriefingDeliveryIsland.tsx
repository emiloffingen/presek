import { absoluteLocaleUrl, localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Radio, Save } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $deliveryPrefs, $syncToken, updateDeliveryPrefs } from '../lib/store.ts';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import {
  buildSyncTokenHeaders,
  buildCsrfHeadersAsync,
  buildDeliveryDigest,
  createDefaultServerDeliverySettings,
  loadDeliveryPreferences,
  normalizeServerDeliverySettings,
  saveDeliveryPreferences,
  setBrowserPermissionStatus,
  toggleDeliveryPreference,
} from '../lib/personalization.js';

function permissionLabel(status: string, lang = 'sr') {
  const isMK = lang === 'mk';
  if (status === 'granted') return isMK ? 'Извештаите во прелистувачот се овозможени' : 'Izveštaji u pretraživaču su omogućeni';
  if (status === 'denied') return isMK ? 'Извештаите во прелистувачот се блокирани' : 'Izveštaji u pretraživaču su blokirani';
  return isMK ? 'Извештаите во прелистувачот не се овозможени' : 'Izveštaji u pretraživaču nisu omogućeni';
}

function decodeVapidPublicKey(key: string) {
  const clean = String(key || '').trim();
  if (!clean) {
    throw new Error('Missing VAPID public key');
  }

  const normalized = clean.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  const raw = globalThis.atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export default function BriefingDeliveryIsland({
  content = '',
  dateLabel = '',
  variant = 'full',
  lang = 'sr'
}: {
  content?: string;
  dateLabel?: string;
  variant?: 'full' | 'summary';
  lang?: string;
}) {
  const profile = useStore($profile);
  const prefs = useStore($deliveryPrefs);
  const syncToken = useStore($syncToken);
  const isMK = lang === 'mk';

  const [serverDelivery, setServerDelivery] = useState(() => createDefaultServerDeliverySettings());
  const [serverStatus, setServerStatus] = useState<'idle' | 'working' | 'done' | 'error'>('idle');
  const [serverMessage, setServerMessage] = useState('');
  const [copyState, setCopyState] = useState<'idle' | 'done' | 'error'>('idle');

  useEffect(() => {
    const permission = typeof Notification !== 'undefined' ? Notification.permission : 'default';
    const nextPrefs = saveDeliveryPreferences(
      { ...loadDeliveryPreferences(), browserPermission: permission },
    );
    updateDeliveryPrefs(nextPrefs);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadRemoteDelivery() {
      if (!syncToken) {
        setServerDelivery(createDefaultServerDeliverySettings());
        return;
      }
      setServerStatus('working');
      setServerMessage('');
      try {
        const res = await fetch('/api/profile/delivery', {
          headers: buildSyncTokenHeaders(syncToken) as Record<string, string>,
        });
        if (!res.ok) throw new Error('load failed');
        const data = await res.json();
        if (!cancelled) {
          setServerDelivery(normalizeServerDeliverySettings(data.subscription || {}));
          setServerStatus('idle');
        }
      } catch {
        if (!cancelled) {
          setServerDelivery(createDefaultServerDeliverySettings());
          setServerStatus('error');
          setServerMessage(isMK ? 'Не можам да ги прочитам закажаните подесувања за достава за овој клуч за синхронизација.' : 'Ne mogu da pročitam zakazana podešavanja za dostavu za ovaj ključ za sinhronizaciju.');
        }
      }
    }

    loadRemoteDelivery();
    return () => {
      cancelled = true;
    };
  }, [syncToken, isMK]);

  const digest = useMemo(
    () => buildDeliveryDigest(content, profile, prefs, lang),
    [content, profile, prefs, lang]
  );

  const mailHref = useMemo(() => {
    const subject = encodeURIComponent(`Presek brifing · ${dateLabel}`);
    const briefingUrl = absoluteLocaleUrl('/briefing', isMK ? 'mk' : 'sr');
    const body = encodeURIComponent(`${digest}\n\n${briefingUrl}`);
    return `mailto:?subject=${subject}&body=${body}`;
  }, [dateLabel, digest, isMK]);

  const requestNotifications = async () => {
    if (typeof Notification === 'undefined') return;
    const status = await Notification.requestPermission();
    const next = setBrowserPermissionStatus(status);
    updateDeliveryPrefs(next);

    if (status === 'granted' && 'serviceWorker' in navigator && 'PushManager' in window) {
        try {
            const vapidRes = await fetch('/api/profile/vapid-key');
            if (vapidRes.ok) {
                const vapidData = await vapidRes.json();
                const pubKey = vapidData.key;

                const reg = await navigator.serviceWorker.register('/sw.js');
                await navigator.serviceWorker.ready;

                const existingSub = await reg.pushManager.getSubscription();
                const sub = existingSub || await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: decodeVapidPublicKey(pubKey)
                });

                if (syncToken) {
                    const payload = {
                        ...serverDelivery,
                        channel: 'webpush',
                        target: JSON.stringify(sub)
                    };
                    updateServerDelivery(payload);

                    await fetch('/api/profile/delivery', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', ...(await buildCsrfHeadersAsync()) },
                        body: JSON.stringify({ token: syncToken, subscription: payload, locale: lang })
                    });
                }
            }
        } catch (e) {
            console.error('Web Push setup failed', e);
        }
    }
  };

  const togglePref = (field: 'morningBriefing' | 'breakingAlerts') => {
    const next = toggleDeliveryPreference(field);
    updateDeliveryPrefs(next);
  };

  const copyDigest = async () => {
    try {
      const briefingUrl = absoluteLocaleUrl('/briefing', isMK ? 'mk' : 'sr');
      await navigator.clipboard.writeText(`${dateLabel}\n\n${digest}\n\n${briefingUrl}`);
      setCopyState('done');
      if (typeof window !== 'undefined') window.setTimeout(() => setCopyState('idle'), 1800);
    } catch {
      setCopyState('error');
      if (typeof window !== 'undefined') window.setTimeout(() => setCopyState('idle'), 2200);
    }
  };

  const updateServerDelivery = (patch: Record<string, unknown>) => {
    setServerDelivery((current) => normalizeServerDeliverySettings({ ...current, ...patch }));
  };

  const saveScheduledDelivery = async () => {
    if (!syncToken) {
      setServerStatus('error');
      setServerMessage(isMK ? 'Прво креирајте или поврзете клуч за синхронизација.' : 'Prvo kreirajte ili povežite ključ za sinhronizaciju.');
      return;
    }

    setServerStatus('working');
    setServerMessage('');
    try {
      const payload = normalizeServerDeliverySettings(serverDelivery);
      const res = await fetch('/api/profile/delivery', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await buildCsrfHeadersAsync()) },
        body: JSON.stringify({
          token: syncToken,
          subscription: payload,
          locale: lang
        }),
      });
      if (!res.ok) throw new Error('save failed');
      const data = await res.json();
      const next = normalizeServerDeliverySettings(data.subscription || {});
      setServerDelivery(next);
      setServerStatus('done');
      setServerMessage(next.isActive
        ? (isMK ? 'Закажаната достава е зачувана во вашиот синхронизиран профил.' : 'Zakazana dostava je sačuvana u vašem sinhroniziranom profilu.')
        : (isMK ? 'Закажаната достава е зачувана, но е неактивна додека не поставите тема.' : 'Zakazana dostava je sačuvana, ali je neaktivna dok ne postavite temu.'));
    } catch {
      setServerStatus('error');
      setServerMessage(isMK ? 'Не можам да ја зачувам закажаната достава во овој момент.' : 'Ne mogu da sačuvam zakazanu dostavu u ovom momentu.');
    }
  };

  const summaryLabel = syncToken
    ? serverDelivery.isActive
      ? (isMK ? 'Синхронизираната достава е активна' : 'Sinhronizirana dostava je aktivna')
      : (isMK ? 'Профилот е синхронизиран, но извештаите се исклучени' : 'Profil je sinhroniziran, ali izveštaji su isključeni')
    : (isMK ? 'Креирајте клуч за синхронизација за да добивате извештаи на сите ваши уреди' : 'Kreirajte ključ za sinhronizaciju da biste dobijali izveštaje na svim vašim uređajima');

  if (variant === 'summary') {
    return (
      <div className="delivery-panel delivery-panel-summary">
        <div className="delivery-status">
          <p className="delivery-status-kicker">
            {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
            <span>{permissionLabel(prefs.browserPermission, lang)}</span>
          </p>
          <p className="delivery-status-copy">{summaryLabel}</p>
        </div>

        <div className="delivery-toggle-list">
          <div className={`delivery-toggle ${serverDelivery.morningBriefing ? 'is-active' : ''}`}>
            <span>{isMK ? 'Утрински брифинг' : 'Jutarnji brifing'}</span>
            <strong>{serverDelivery.morningBriefing ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`}>
            <span>{isMK ? 'Неделен преглед' : 'Nedeljni pregled'}</span>
            <strong>{serverDelivery.weeklyDigest ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span>{isMK ? 'Итни вести' : 'Hitne vesti'}</span>
            <strong>{serverDelivery.breakingTopics || serverDelivery.breakingSources ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href={localePathForLang('/settings', isMK ? 'mk' : 'sr')} className="delivery-action">
            <Radio size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{isMK ? 'Отворете подесувања' : 'Otvorite podešavanja'}</span>
            </span>
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{copyState === 'done' ? (isMK ? 'Копирано' : 'Kopirano') : copyState === 'error' ? (isMK ? 'Копирањето не успеа' : 'Kopiranje nije uspelo') : (isMK ? 'Копирај текстуална верзија' : 'Kopiraj tekstualnu verziju')}</span>
            </span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="delivery-panel space-y-8">
      <div className="delivery-status">
        <p className="delivery-status-kicker">
          {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
          <span>{permissionLabel(prefs.browserPermission, lang)}</span>
        </p>
        <p className="delivery-status-copy">
          {isMK
            ? 'Доставата е поврзана со темите и изворите што ги следите во овој прелистувач. Започнете со локални извештаи и верзија за споделување, а потоа додајте синхронизирана достава помеѓу уредите.'
            : 'Dostava je vezana za teme i izvore koje pratite u ovom pretraživaču. Započnite sa lokalnim izveštajima i verzijom za deljenje, a zatim dodajte sinhroniziranu dostavu između uređaja.'}
        </p>
      </div>

      <div className="delivery-toggle-list space-y-3">
        <button type="button" className={`custom-toggle-btn w-full ${prefs.morningBriefing ? 'is-active' : ''}`} onClick={() => togglePref('morningBriefing')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">{isMK ? 'Утрински брифинг' : 'Jutarnji brifing'}</span>
            <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Локален преглед на денот во овој прелистувач.' : 'Lokalni pregled dana u ovom pretraživaču.'}</span>
          </span>
          <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${prefs.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.morningBriefing ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
        </button>
        <button type="button" className={`custom-toggle-btn w-full ${prefs.breakingAlerts ? 'is-active' : ''}`} onClick={() => togglePref('breakingAlerts')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">{isMK ? 'Итни извештаи' : 'Hitna izveštaja'}</span>
            <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Брзи сигнали кога следената приказна ќе забрза.' : 'Brzi signali kada pratena priča ubrza.'}</span>
          </span>
          <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${prefs.breakingAlerts ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.breakingAlerts ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{isMK ? 'Овозможи извештаи во прелистувачот' : 'Omogući izveštaje u pretraživaču'}</span>
            <span className="delivery-action-note">{isMK ? 'Активирај локални push пораки за овој уред.' : 'Aktiviraj lokalne push poruke za ovaj uređaj.'}</span>
          </span>
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{copyState === 'done' ? (isMK ? 'Копирано' : 'Kopirano') : copyState === 'error' ? (isMK ? 'Копирањето не успеа' : 'Kopiranje nije uspelo') : (isMK ? 'Копирај верзија за достава' : 'Kopiraj verziju za dostavu')}</span>
            <span className="delivery-action-note">{isMK ? 'Кратка текстуална верзија за споделување.' : 'Kratka tekstualna verzija za deljenje.'}</span>
          </span>
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{isMK ? 'Споделете преку е-пошта' : 'Delite putem e-pošte'}</span>
            <span className="delivery-action-note">{isMK ? 'Го отвора вашиот е-маил клиент со подготвениот преглед.' : 'Otvara vaš e-mail klijent sa pripremljenim pregledom.'}</span>
          </span>
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">{isMK ? 'Преглед на достава' : 'Pregled dostave'}</p>
        <pre className="digest-paper-view">{digest || (isMK ? 'Прегледот на достава ќе се појави овде кога ќе биде достапен брифинг.' : 'Pregled dostave će se pojaviti ovde kada bude dostupan brifing.')}</pre>
      </div>

      <div className="scheduled-delivery-panel pt-6 border-t border-border/40">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>{isMK ? 'Закажана достава' : 'Zakazana dostava'}</span>
        </p>
        <p className="scheduled-delivery-copy">
          {isMK
            ? 'Зачувајте `ntfy` тема со вашиот клуч за синхронизација за да добивате серверски утрински брифинзи, неделни дигести и извештаи за следените теми или извори.'
            : 'Sačuvajte `ntfy` temu sa vašim ključem za sinhronizaciju da biste dobijali serverske jutarnje brifinge, nedeljne digestove i izveštaje za pratene teme ili izvore.'}
        </p>

        <label className="scheduled-delivery-label">
          <span>{isMK ? 'Ntfy тема' : 'Ntfy tema'}</span>
          <input
            type="text"
            className="account-sync-input"
            value={serverDelivery.target}
            onChange={(e) => updateServerDelivery({ target: e.target.value })}
            placeholder={isMK ? "моја-пресек-тема" : "moja-presek-tema"}
          />
        </label>

        <div className="delivery-toggle-list space-y-3 mt-4">
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.morningBriefing ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{isMK ? 'Утрински ntfy брифинг' : 'Jutarnji ntfy brifing'}</span>
              <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Серверски испорачан преглед во вашата `ntfy` тема.' : 'Serverski isporučen pregled u vašu `ntfy` temu.'}</span>
            </span>
            <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.morningBriefing ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.weeklyDigest ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{isMK ? 'Неделен дигест' : 'Nedeljni digest'}</span>
              <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Подобар резиме-преглед на темите што сте ги следеле.' : 'Pobolignan rezime-pregled tema koje ste pratili.'}</span>
            </span>
            <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.weeklyDigest ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.weeklyDigest ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.breakingTopics ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{isMK ? 'Извештаи за следени теми' : 'Izveštaji za pratene teme'}</span>
              <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Се активира кога вашите теми ќе добијат нов силен кластер.' : 'Aktivira se kada vaše teme dobiju novi snažan klaster.'}</span>
            </span>
            <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.breakingTopics ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingTopics ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.breakingSources ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{isMK ? 'Извештаи за следени извори' : 'Izveštaji za praćene izvore'}</span>
              <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'Следи кога избраниот извор прв ќе отвори Важна приказна.' : 'Prati kada izabrani izvor prvo otvori Važnu priču.'}</span>
            </span>
            <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.breakingSources ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingSources ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.isActive ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{isMK ? 'Закажаната достава е активна' : 'Zakazana dostava je aktivna'}</span>
              <span className="block text-[10px] md:text-[11px] text-muted-foreground mt-0.5">{isMK ? 'главен прекинувач за серверска достава на овој профил.' : 'glavni prekidač za serversku dostavu na ovom profilu.'}</span>
            </span>
            <strong className={`text-[9px] md:text-[10px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.isActive ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.isActive ? (isMK ? 'Овозможено' : 'Omogućeno') : (isMK ? 'Оневозможено' : 'Onemogućeno')}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action mt-6" onClick={saveScheduledDelivery}>
          <Save size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{isMK ? 'Зачувај закажана достава' : 'Sačuvaj zakazanu dostavu'}</span>
            <span className="delivery-action-note">{isMK ? 'Снима `ntfy` поставки во синхронизираниот профил.' : 'Snima `ntfy` postavke u sinhronizirani profil.'}</span>
          </span>
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>
    </div>
  );
}
