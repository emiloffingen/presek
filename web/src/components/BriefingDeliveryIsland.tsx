import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Radio, Save } from 'lucide-react';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import {
  buildSyncTokenHeaders,
  buildDeliveryDigest,
  createDefaultServerDeliverySettings,
  loadDeliveryPreferences,
  loadReaderProfile,
  loadSyncToken,
  normalizeServerDeliverySettings,
  saveDeliveryPreferences,
  setBrowserPermissionStatus,
  subscribeToReaderProfile,
  toggleDeliveryPreference,
} from '../lib/personalization.js';

function permissionLabel(status: string) {
  if (status === 'granted') return 'Известувањата во прелистувач се вклучени';
  if (status === 'denied') return 'Известувањата во прелистувач се блокирани';
  return 'Известувањата во прелистувач не се вклучени';
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
  const [profile, setProfile] = useState(() => loadReaderProfile());
  const [prefs, setPrefs] = useState(() => loadDeliveryPreferences());
  const [syncToken, setSyncToken] = useState(() => loadSyncToken());
  const [serverDelivery, setServerDelivery] = useState(() => createDefaultServerDeliverySettings());
  const [serverStatus, setServerStatus] = useState<'idle' | 'working' | 'done' | 'error'>('idle');
  const [serverMessage, setServerMessage] = useState('');
  const [copyState, setCopyState] = useState<'idle' | 'done' | 'error'>('idle');

  useEffect(() => {
    const permission = typeof Notification !== 'undefined' ? Notification.permission : 'default';
    const nextPrefs = saveDeliveryPreferences(
      { ...loadDeliveryPreferences(), browserPermission: permission },
    );
    setPrefs(nextPrefs);
    setProfile(loadReaderProfile());
  }, []);

  useEffect(() => subscribeToReaderProfile(setProfile), []);

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
    const subject = encodeURIComponent(`Пресек брифинг · ${dateLabel}`);
    const body = encodeURIComponent(`${digest}\n\nhttps://presek.live/briefing`);
    return `mailto:?subject=${subject}&body=${body}`;
  }, [dateLabel, digest]);

  const requestNotifications = async () => {
    if (typeof Notification === 'undefined') return;
    const status = await Notification.requestPermission();
    const next = setBrowserPermissionStatus(status);
    setPrefs(next);

    if (status === 'granted' && 'serviceWorker' in navigator && 'PushManager' in window) {
        try {
            const vapidRes = await fetch('/api/profile/vapid-key');
            if (vapidRes.ok) {
                const vapidData = await vapidRes.json();
                const pubKey = vapidData.key;
                
                const reg = await navigator.serviceWorker.register('/sw.js');
                await navigator.serviceWorker.ready;
                
                const sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: pubKey
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
    setPrefs(next);
  };

  const copyDigest = async () => {
    try {
      await navigator.clipboard.writeText(`${dateLabel}\n\n${digest}\n\nhttps://presek.live/briefing`);
      setCopyState('done');
      window.setTimeout(() => setCopyState('idle'), 1800);
    } catch {
      setCopyState('error');
      window.setTimeout(() => setCopyState('idle'), 2200);
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
      : 'Sync е поврзан, но закажаната достава сè уште е исклучена'
    : 'Креирајте клуч за синхронизација за ова да стане вистинска достава меѓу уреди';

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
            <span>Неделен дигест</span>
            <strong>{serverDelivery.weeklyDigest ? 'Вклучено' : 'Исклучено'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span>Итни известувања</span>
            <strong>{serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'Вклучено' : 'Исклучено'}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href="/settings" className="delivery-action">
            <Radio size={14} /> Отвори поставки за достава
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} /> {copyState === 'done' ? 'Копирано' : copyState === 'error' ? 'Копирањето не успеа' : 'Копирај верзија за достава'}
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

      <div className="delivery-toggle-list">
        <button type="button" className={`delivery-toggle ${prefs.morningBriefing ? 'is-active' : ''}`} onClick={() => togglePref('morningBriefing')}>
          <span>Утрински брифинг</span>
          <strong>{prefs.morningBriefing ? 'Вклучено' : 'Исклучено'}</strong>
        </button>
        <button type="button" className={`delivery-toggle ${prefs.breakingAlerts ? 'is-active' : ''}`} onClick={() => togglePref('breakingAlerts')}>
            <span>Итни известувања</span>
          <strong>{prefs.breakingAlerts ? 'Вклучено' : 'Исклучено'}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} /> Вклучи известувања во прелистувач
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} /> {copyState === 'done' ? 'Копирано' : copyState === 'error' ? 'Копирањето не успеа' : 'Копирај верзија за достава'}
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} /> Сподели преку е-пошта
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

        <div className="delivery-toggle-list">
          <button type="button" className={`delivery-toggle ${serverDelivery.morningBriefing ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span>Утрински ntfy брифинг</span>
            <strong>{serverDelivery.morningBriefing ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span>Неделен дигест</span>
            <strong>{serverDelivery.weeklyDigest ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.breakingTopics ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span>Известувања за следени теми</span>
            <strong>{serverDelivery.breakingTopics ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.breakingSources ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span>Известувања за следени извори</span>
            <strong>{serverDelivery.breakingSources ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.isActive ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span>Закажаната достава е активна</span>
            <strong>{serverDelivery.isActive ? 'Вклучено' : 'Исклучено'}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action" onClick={saveScheduledDelivery}>
          <Save size={14} /> Зачувај закажана достава
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>

      <AccountSyncIsland onTokenChange={setSyncToken} />
    </div>
  );
}
