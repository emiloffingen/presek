import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Send, Radio, Save } from 'lucide-react';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import {
  buildDeliveryDigest,
  createDefaultServerDeliverySettings,
  loadDeliveryPreferences,
  loadReaderProfile,
  loadSyncToken,
  normalizeServerDeliverySettings,
  saveDeliveryPreferences,
  setBrowserPermissionStatus,
  toggleDeliveryPreference,
} from '../lib/personalization.js';

function permissionLabel(status: string) {
  if (status === 'granted') return 'Browser alerts enabled';
  if (status === 'denied') return 'Browser alerts blocked';
  return 'Browser alerts not enabled';
}

export default function BriefingDeliveryIsland({
  content = '',
  dateLabel = '',
}: {
  content?: string;
  dateLabel?: string;
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
        const res = await fetch(`/api/profile/delivery?token=${encodeURIComponent(syncToken)}`);
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
          setServerMessage('Could not load scheduled delivery settings for this sync key.');
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

  const telegramHref = useMemo(() => {
    const text = encodeURIComponent(`${dateLabel}\n\n${digest}\n\nhttps://presek.live/briefing`);
    return `https://t.me/share/url?url=${encodeURIComponent('https://presek.live/briefing')}&text=${text}`;
  }, [dateLabel, digest]);

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
      setServerMessage('Create or connect a sync key first.');
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
      setServerMessage(next.isActive ? 'Scheduled delivery is saved to your synced profile.' : 'Scheduled delivery is saved but inactive until a topic is set.');
    } catch {
      setServerStatus('error');
      setServerMessage('Could not save scheduled delivery right now.');
    }
  };

  return (
    <div className="delivery-panel">
      <div className="delivery-status">
        <p className="delivery-status-kicker">
          {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
          <span>{permissionLabel(prefs.browserPermission)}</span>
        </p>
        <p className="delivery-status-copy">
          Delivery is tied to your followed topics and sources on this browser. Start with local alerts and shareable briefing output before adding account-based delivery.
        </p>
      </div>

      <div className="delivery-toggle-list">
        <button type="button" className={`delivery-toggle ${prefs.morningBriefing ? 'is-active' : ''}`} onClick={() => togglePref('morningBriefing')}>
          <span>Morning briefing</span>
          <strong>{prefs.morningBriefing ? 'On' : 'Off'}</strong>
        </button>
        <button type="button" className={`delivery-toggle ${prefs.breakingAlerts ? 'is-active' : ''}`} onClick={() => togglePref('breakingAlerts')}>
          <span>Breaking alerts</span>
          <strong>{prefs.breakingAlerts ? 'On' : 'Off'}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} /> Enable browser alerts
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} /> {copyState === 'done' ? 'Copied' : copyState === 'error' ? 'Copy failed' : 'Copy delivery version'}
        </button>
        <a href={telegramHref} target="_blank" rel="noopener noreferrer" className="delivery-action">
          <Send size={14} /> Share to Telegram
        </a>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} /> Share by email
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">Delivery preview</p>
        <pre>{digest || 'Your delivery preview will appear here once a briefing is available.'}</pre>
      </div>

      <div className="scheduled-delivery-panel">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>Scheduled delivery</span>
        </p>
        <p className="scheduled-delivery-copy">
          Save an `ntfy` topic against your sync key to receive server-side morning briefings, weekly digests, and followed-topic or followed-source alerts.
        </p>

        <label className="scheduled-delivery-label">
          <span>Ntfy topic</span>
          <input
            type="text"
            className="account-sync-input"
            value={serverDelivery.target}
            onChange={(e) => updateServerDelivery({ target: e.target.value })}
            placeholder="your-presek-topic"
          />
        </label>

        <div className="delivery-toggle-list">
          <button type="button" className={`delivery-toggle ${serverDelivery.morningBriefing ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span>Morning ntfy briefing</span>
            <strong>{serverDelivery.morningBriefing ? 'On' : 'Off'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span>Weekly digest</span>
            <strong>{serverDelivery.weeklyDigest ? 'On' : 'Off'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.breakingTopics ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span>Alerts for followed topics</span>
            <strong>{serverDelivery.breakingTopics ? 'On' : 'Off'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.breakingSources ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span>Alerts for followed sources</span>
            <strong>{serverDelivery.breakingSources ? 'On' : 'Off'}</strong>
          </button>
          <button type="button" className={`delivery-toggle ${serverDelivery.isActive ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span>Scheduled delivery active</span>
            <strong>{serverDelivery.isActive ? 'On' : 'Off'}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action" onClick={saveScheduledDelivery}>
          <Save size={14} /> Save scheduled delivery
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>

      <AccountSyncIsland onTokenChange={setSyncToken} />
    </div>
  );
}
