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
  if (status === 'granted') return 'Izvestuvanjata vo prelistuvac se vkluceni';
  if (status === 'denied') return 'Izvestuvanjata vo prelistuvac se blokirani';
  return 'Izvestuvanjata vo prelistuvac ne se vkluceni';
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
          setServerMessage('Ne mozev da im vcitam zakazanite postavki za dostava za ovoj kluc za sinhronizacija.');
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
      setServerMessage('Prvo kreirajte ili povrzete kluc za sinhronizacija.');
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
      setServerMessage(next.isActive ? 'Zakazanata dostava e zacuvana vo vasiot sinhroniziran profil.' : 'Zakazanata dostava e zacuvana, no e neaktivna dodeka ne postavite tema.');
    } catch {
      setServerStatus('error');
      setServerMessage('Ne mozev da me zacuvam zakazanata dostava vo momentov.');
    }
  };

  const summaryLabel = syncToken
    ? serverDelivery.isActive
      ? 'Sinhroniziranata dostava e aktivna'
      : 'Profilot e sinhroniziran, no izvestuvanjata se iskluceni'
    : 'Kreirajte kluc za sinhronizacija za da dobivate izvestuvanja na site vasi uredi';

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
            <span>Utrinski brifing</span>
            <strong>{serverDelivery.morningBriefing ? 'Vkluceno' : 'Iskluceno'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`}>
            <span>Nedelen pregled</span>
            <strong>{serverDelivery.weeklyDigest ? 'Vkluceno' : 'Iskluceno'}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span>Udarni vesti</span>
            <strong>{serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'Vkluceno' : 'Iskluceno'}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href="/settings" className="delivery-action">
            <Radio size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">Otvori postavki</span>
            </span>
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{copyState === 'done' ? 'Kopirano' : copyState === 'error' ? 'Kopiranjeto ne uspea' : 'Kopiraj tekstualna verzija'}</span>
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
          Dostavata e vrzana za temite i izvorite sto im sledite na ovoj prelistuvac. Pocnete so lokalni izvestuvanja i verzija za spodeluvanje, pa potoa dodajte sinhronizirana dostava medju uredi.
        </p>
      </div>

      <div className="delivery-toggle-list space-y-4">
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.morningBriefing ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('morningBriefing')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Utrinski brifing</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Lokalen pregled na denot na ovoj prelistuvac.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.morningBriefing ? 'Vkluceno' : 'Iskluceno'}</strong>
        </button>
        <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${prefs.breakingAlerts ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => togglePref('breakingAlerts')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">Itni izvestuvanja</span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">Brzi signali koga sledenata prica zabrzuva.</span>
          </span>
          <strong className={`text-[10px] font-black uppercase tracking-widest ${prefs.breakingAlerts ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{prefs.breakingAlerts ? 'Vkluceno' : 'Iskluceno'}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Vkluci izvestuvanja vo prelistuvac</span>
            <span className="delivery-action-note">Aktivira lokalni push poraki za ovoj ured.</span>
          </span>
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{copyState === 'done' ? 'Kopirano' : copyState === 'error' ? 'Kopiranjeto ne uspea' : 'Kopiraj verzija za dostava'}</span>
            <span className="delivery-action-note">Kratka tekstualna verzija za spodeluvanje.</span>
          </span>
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Spodeli preku e-posta</span>
            <span className="delivery-action-note">Go otvora vasiot mail klient so podgotven pregled.</span>
          </span>
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">Pregled na dostavata</p>
        <pre>{digest || 'Pregledot na dostavata ce se pojavi tuka stom ima dostapen brifing.'}</pre>
      </div>

      <div className="scheduled-delivery-panel">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>Zakazana dostava</span>
        </p>
        <p className="scheduled-delivery-copy">
          Zacuvajte `ntfy` tema so vasiot kluc za sinhronizacija za da dobivate serverski utrinski brifinzi, nedelni digesti i izvestuvanja za sledenite temi ili izvori.
        </p>

        <label className="scheduled-delivery-label">
          <span>Ntfy tema</span>
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
              <span className="block font-sans font-bold text-sm">Utrinski ntfy brifing</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Serverski isporacan pregled vo vasata `ntfy` tema.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.morningBriefing ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.morningBriefing ? 'Vkluceno' : 'Iskluceno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.weeklyDigest ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Nedelen digest</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Pobaven rezime-pregled na temite sto ste im sledele.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.weeklyDigest ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.weeklyDigest ? 'Vkluceno' : 'Iskluceno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingTopics ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Izvestuvanja za sledeni temi</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Se aktivira koga vasite temi dobivaat nov silen klaster.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingTopics ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingTopics ? 'Vkluceno' : 'Iskluceno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.breakingSources ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Izvestuvanja za Praceni izvori</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Sledi koga izbran izvor prv otvora Vazna prica.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.breakingSources ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.breakingSources ? 'Vkluceno' : 'Iskluceno'}</strong>
          </button>
          <button type="button" className={`flex w-full items-center justify-between p-4 rounded-xl border transition ${serverDelivery.isActive ? 'bg-nyt-accent/10 border-nyt-accent' : 'bg-secondary/5 border-border'}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">Zakazanata dostava e aktivna</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">Glaven prekinuvac za serverskata dostava na ovoj profil.</span>
            </span>
            <strong className={`text-[10px] font-black uppercase tracking-widest ${serverDelivery.isActive ? 'text-nyt-accent' : 'text-muted-foreground'}`}>{serverDelivery.isActive ? 'Vkluceno' : 'Iskluceno'}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action" onClick={saveScheduledDelivery}>
          <Save size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">Zacuvaj zakazana dostava</span>
            <span className="delivery-action-note">Gi snima `ntfy` postavkite vo sinhroniziraniot profil.</span>
          </span>
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>
    </div>
  );
}
