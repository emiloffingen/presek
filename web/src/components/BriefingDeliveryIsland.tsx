import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Radio, Save } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $deliveryPrefs, $syncToken, updateDeliveryPrefs } from '../lib/store.ts';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import {
  buildSyncTokenHeaders,
  buildDeliveryDigest,
  createDefaultServerDeliverySettings,
  loadDeliveryPreferences,
  normalizeServerDeliverySettings,
  saveDeliveryPreferences,
  setBrowserPermissionStatus,
  toggleDeliveryPreference,
} from '../lib/personalization.js';

function permissionLabel(status: string) {
  if (status === 'granted') return 'Известувањата во прелистувач се вклучени';
  if (status === 'denied') return 'Известувањата во прелистувач се блокирани';
  return 'Известувањата во прелистувач не се вклучени';
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
}: {
  content?: string;
  dateLabel?: string;
  variant?: 'full' | 'summary';
}) {
  const profile = useStore($profile);
  const prefs = useStore($deliveryPrefs);
  const syncToken = useStore($syncToken);
  
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
          setServerMessage('Не можев да ги вчитам закажаните поставки за достава за овој клуч за синхронизација.');
        }
      }
    }

    loadRemoteDelivery();
    return () => {
      cancelled = true;
    };
  }, [syncToken]);

  const digest = useMemo(
    () => buildDeliveryDigest(content, profile, prefs),
    [content, profile, prefs]
  );

  const mailHref = useMemo(() => {
    const subject = encodeURIComponent(`Presek брифинг · ${dateLabel}`);
    const body = encodeURIComponent(`${digest}\n\nhttps://presek.live/briefing`);
    return `mailto:?subject=${subject}&body=${body}`;
  }, [dateLabel, digest]);

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
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token: syncToken, subscription: payload })
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
      await navigator.clipboard.writeText(`${dateLabel}\n\n${digest}\n\nhttps://presek.live/briefing`);
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
      setServerMessage('Прво креирајте или поврзете клуч за синхронизација.');
      return;
    }

    setServerStatus('working');
    setServerMessage('');
    try {
      const payload = normalizeServerDeliverySettings(serverDelivery);
      const res = await fetch('/api/profile/delivery', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: syncToken,
          subscription: payload,
        }),
      });
      if (!res.ok) throw new Error('save failed');
      const data = await res.json();
      const next = normalizeServerDeliverySettings(data.subscription || {});
      setServerDelivery(next);
      setServerStatus('done');
      setServerMessage(next.isActive ? 'Закажаната достава е зачувана во вашиот синхронизиран профил.' : 'Закажаната достава е зачувана, но е неактивна додека не поставите тема.');
    } catch {
      setServerStatus('error');
      setServerMessage('Не можев да ја зачувам закажаната достава во моментов.');
    }
  };

  const summaryLabel = syncToken
    ? serverDelivery.isActive
      ? 'Синхронизираната достава е активна'
      : 'Профилот е синхронизиран, но известувањата се исклучени'
    : 'Креирајте клуч за синхронизација за да добивате известувања на сите ваши уреди';

  if (variant === 'summary') {
    return (
      <div className="delivery-panel delivery-panel-summary">
        <div className="delivery-status">
          <p className="delivery-status-kicker">
            {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
            <span>{permissionLabel(prefs.browserPermission)}</span>
          </p>
          <p className="delivery-status-copy">{summaryLabel}</p>
        </div>

        <div className="delivery-toggle-list">
          <div className={`delivery-toggle ${serverDelivery.morningBriefing ? 'is-active' : ''}`}>
            <span>Утрински брифинг</span>
            <strong>{serverDelivery.morningBriefing ? 'Вклучено' : 'Исклучено'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`}>
            <span>Неделен преглед</span>
            <strong>{serverDelivery.weeklyDigest ? 'Вклучено' : 'Исклучено'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span>Ударни вести</span>
            <strong>{serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'Вклучено' : 'Исклучено'}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href="/settings" className="delivery-action">
            <Radio size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">Отвори поставки</span>
            </span>
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{copyState === 'done' ? 'Копирано' : copyState === 'error' ? 'Копирањето не успеа' : 'Копирај текстуална верзија'}</span>
            </span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="delivery-panel">
      <div className="delivery-status">
        <p className="delivery-status-kicker">
          {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
          <span>{permissionLabel(prefs.browserPermission)}</span>
        </p>
        <p className="delivery-status-copy">
          Доставата е врзана за темите и изворите што ги следите на овој прелистувач. Почнете со локални известувања и верзија за споделување, па потоа додајте синхронизирана достава меѓу уреди.
        </p>
      </div>

      <div className="delivery-toggle-list space-y-4">
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.morningBriefing ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('morningBriefing')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Утрински брифинг</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Локален преглед на денот на овој прелистувач.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.morningBriefing ? 'Вклучено' : 'Исклучено'}</strong>
        </button>
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.breakingAlerts ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('breakingAlerts')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Итни известувања</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Брзи сигнали кога следената приказна забрзува.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.breakingAlerts ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.breakingAlerts ? 'Вклучено' : 'Исклучено'}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Вклучи известувања во прелистувач</span>
            <span className="delivery-action-note">Активира локални push пораки за овој уред.</span>
          </span>
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{copyState === 'done' ? 'Копирано' : copyState === 'error' ? 'Копирањето не успеа' : 'Копирај верзија за достава'}</span>
            <span className="delivery-action-note">Кратка текстуална верзија за споделување.</span>
          </span>
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Сподели преку е-пошта</span>
            <span className="delivery-action-note">Го отвора вашиот mail клиент со подготвен преглед.</span>
          </span>
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">Преглед на доставата</p>
        <pre>{digest || 'Прегледот на доставата ќе се појави тука штом има достапен брифинг.'}</pre>
      </div>

      <div className="scheduled-delivery-panel">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>Закажана достава</span>
        </p>
        <p className="scheduled-delivery-copy">
          Зачувајте `ntfy` тема со вашиот клуч за синхронизација за да добивате серверски утрински брифинзи, неделни дигести и известувања за следените теми или извори.
        </p>

        <label className="scheduled-delivery-label">
          <span>Ntfy тема</span>
          <input
            type="text"
            className="account-sync-input"
            value={serverDelivery.target}
            onChange={(e) => updateServerDelivery({ target: e.target.value })}
            placeholder="mojata-presek-tema"
          />
        </label>

        <div className="delivery-toggle-list space-y-4">
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.morningBriefing ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Утрински ntfy брифинг</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Серверски испорачан преглед во вашата `ntfy` тема.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.morningBriefing ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.weeklyDigest ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Неделен дигест</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Побавен резиме-преглед на темите што сте ги следеле.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.weeklyDigest ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.weeklyDigest ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingTopics ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Известувања за следени теми</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Се активира кога вашите теми добиваат нов силен кластер.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingTopics ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingTopics ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingSources ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Известувања за следени извори</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Следи кога избран извор прв отвора важна приказна.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingSources ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingSources ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.isActive ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Закажаната достава е активна</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Главен прекинувач за серверската достава на овој профил.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.isActive ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.isActive ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action" onClick={saveScheduledDelivery}>
          <Save size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Зачувај закажана достава</span>
            <span className="delivery-action-note">Ги снима `ntfy` поставките во синхронизираниот профил.</span>
          </span>
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>
    </div>
  );
}
