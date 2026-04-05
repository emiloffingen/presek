import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Send } from 'lucide-react';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import {
  buildDeliveryDigest,
  loadDeliveryPreferences,
  loadReaderProfile,
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
  const [copyState, setCopyState] = useState<'idle' | 'done' | 'error'>('idle');

  useEffect(() => {
    const permission = typeof Notification !== 'undefined' ? Notification.permission : 'default';
    const nextPrefs = saveDeliveryPreferences(
      { ...loadDeliveryPreferences(), browserPermission: permission },
    );
    setPrefs(nextPrefs);
    setProfile(loadReaderProfile());
  }, []);

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

      <AccountSyncIsland />
    </div>
  );
}
