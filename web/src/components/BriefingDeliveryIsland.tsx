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
  if (status === 'granted') return 'Izveštaji u pretraživaču su omogućeni';
  if (status === 'denied') return 'Izveštaji u pretraživaču su blokirani';
  return 'Izveštaji u pretraživaču nisu omogućeni';
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
          setServerMessage('Ne mogu da pročitam zakazana podešavanja za dostavu za ovaj ključ za sinhronizaciju.');
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
    const subject = encodeURIComponent(`Presek brifing · ${dateLabel}`);
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
      setServerMessage('Prvo kreirajte ili povežite ključ za sinhronizaciju.');
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
      setServerMessage(next.isActive ? 'Zakazana dostava je sačuvana u vašem sinhroniziranom profilu.' : 'Zakazana dostava je sačuvana, ali je neaktivna dok ne postavite temu.');
    } catch {
      setServerStatus('error');
      setServerMessage('Ne mogu da sačuvam zakazanu dostavu u ovom momentu.');
    }
  };

  const summaryLabel = syncToken
    ? serverDelivery.isActive
      ? 'Sinhronizirana dostava je aktivna'
      : 'Profil je sinhroniziran, ali izveštaji su isključeni'
    : 'Kreirajte ključ za sinhronizaciju da biste dobijali izveštaje na svim vašim uređajima';

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
            <span>Jutarnji brifing</span>
            <strong>{serverDelivery.morningBriefing ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`}>
            <span>Nedeljni pregled</span>
            <strong>{serverDelivery.weeklyDigest ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span> Hitne vesti</span>
            <strong>{serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href="/settings" className="delivery-action">
            <Radio size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">Otvorite podešavanja</span>
            </span>
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{copyState === 'done' ? 'Kopirano' : copyState === 'error' ? 'Kopiranje nije uspelo' : 'Kopiraj tekstualnu verziju'}</span>
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
          Dostava je vezana za teme i izvore koje pratite u ovom pretraživaču. Započnite sa lokalnim izveštajima i verzijom za deljenje, a zatim dodajte sinhroniziranu dostavu između uređaja.
        </p>
      </div>

      <div className="delivery-toggle-list space-y-4">
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.morningBriefing ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('morningBriefing')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Jutarnji brifing</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Lokalni pregled dana u ovom pretraživaču.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.morningBriefing ? 'Omogućeno' : 'Onemogućeno'}</strong>
        </button>
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.breakingAlerts ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('breakingAlerts')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Hitna izveštaja</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Brzi signali kada pratena priča ubrza.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.breakingAlerts ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.breakingAlerts ? 'Omogućeno' : 'Onemogućeno'}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Omogući izveštaje u pretraživaču</span>
            <span className="delivery-action-note">Aktiviraj lokalne push poruke za ovaj uređaj.</span>
          </span>
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{copyState === 'done' ? 'Kopirano' : copyState === 'error' ? 'Kopiranje nije uspelo' : 'Kopiraj verziju za dostavu'}</span>
            <span className="delivery-action-note">Kratka tekstualna verzija za deljenje.</span>
          </span>
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Delite putem e-pošte</span>
            <span className="delivery-action-note">Otvara vaš e-mail klijent sa pripremljenim pregledom.</span>
          </span>
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">Pregled dostave</p>
        <pre>{digest || 'Pregled dostave će se pojaviti ovde kada bude dostupan brifing.'}</pre>
      </div>

      <div className="scheduled-delivery-panel">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>Zakazana dostava</span>
        </p>
        <p className="scheduled-delivery-copy">
          Sačuvajte `ntfy` temu sa vašim ključem za sinhronizaciju da biste dobijali serverske jutarnje brifinge, nedeljne digestove i izveštaje za pratene teme ili izvore.
        </p>

        <label className="scheduled-delivery-label">
          <span>Ntfy tema</span>
          <input
            type="text"
            className="account-sync-input"
            value={serverDelivery.target}
            onChange={(e) => updateServerDelivery({ target: e.target.value })}
            placeholder="moja-presek-tema"
          />
        </label>

        <div className="delivery-toggle-list space-y-4">
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.morningBriefing ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Jutarnji ntfy brifing</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Serverski isporučen pregled u vašu `ntfy` temu.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.morningBriefing ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.weeklyDigest ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Nedeljni digest</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Pobolignan rezime-pregled tema koje ste pratili.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.weeklyDigest ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.weeklyDigest ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingTopics ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Izveštaji za pratene teme</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Aktivira se kada vaše teme dobiju novi snažan klaster.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingTopics ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingTopics ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingSources ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Izveštaji za praćene izvore</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Prati kada izabrani izvor prvo otvori Važnu priču.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingSources ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingSources ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.isActive ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Zakazana dostava je aktivna</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Glavni prekidač za serversku dostavu na ovom profilu.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.isActive ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.isActive ? 'Omogućeno' : 'Onemogućeno'}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action" onClick={saveScheduledDelivery}>
          <Save size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Sačuvaj zakazanu dostavu</span>
            <span className="delivery-action-note">Snima `ntfy` postavke u sinhronizirani profil.</span>
          </span>
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>
    </div>
  );
}
