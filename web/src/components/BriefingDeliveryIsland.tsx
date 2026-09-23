import { absoluteLocaleUrl, localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import { Bell, BellRing, Copy, Mail, Radio, Save } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, $deliveryPrefs, $syncToken, updateDeliveryPrefs } from '../lib/store.ts';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';
import AccountSyncIsland from './AccountSyncIsland.tsx';
import MorningEmailSignup from './MorningEmailSignup.tsx';
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

function permissionLabel(status: string, t: (key: string) => string) {
  if (status === 'granted') return t('settings.delivery.permission_granted');
  if (status === 'denied') return t('settings.delivery.permission_denied');
  return t('settings.delivery.permission_default');
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
  lang = 'mk'
}: {
  content?: string;
  dateLabel?: string;
  variant?: 'full' | 'summary';
  lang?: 'sr' | 'mk';
}) {
  const profile = useStore($profile);
  const prefs = useStore($deliveryPrefs);
  const syncToken = useStore($syncToken);
  const t = useClientTranslations(lang, settings);
  const enabledLabel = (on: boolean) => on ? t('settings.delivery.enabled') : t('settings.delivery.disabled');

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
          setServerMessage(t('settings.delivery.load_error'));
        }
      }
    }

    loadRemoteDelivery();
    return () => {
      cancelled = true;
    };
  }, [syncToken, lang, t]);

  const digest = useMemo(
    () => buildDeliveryDigest(content, profile, prefs, lang),
    [content, profile, prefs, lang]
  );

  const mailHref = useMemo(() => {
    const subject = encodeURIComponent(`Presek brifing · ${dateLabel}`);
    const briefingUrl = absoluteLocaleUrl('/briefing', lang);
    const body = encodeURIComponent(`${digest}\n\n${briefingUrl}`);
    return `mailto:?subject=${subject}&body=${body}`;
  }, [dateLabel, digest, lang]);

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

                const reg = await navigator.serviceWorker.register('/sw.js', { type: 'module' });
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
      const briefingUrl = absoluteLocaleUrl('/briefing', lang);
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
      setServerMessage(t('settings.delivery.sync_first'));
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
      setServerMessage(next.isActive ? t('settings.delivery.save_active') : t('settings.delivery.save_inactive'));
    } catch {
      setServerStatus('error');
      setServerMessage(t('settings.delivery.save_error'));
    }
  };

  const summaryLabel = syncToken
    ? serverDelivery.isActive
      ? t('settings.delivery.summary_active')
      : t('settings.delivery.summary_sync_inactive')
    : t('settings.delivery.summary_local');

  if (variant === 'summary') {
    return (
      <div className="delivery-panel delivery-panel-summary">
        <div className="delivery-status">
          <p className="delivery-status-kicker">
            {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
            <span>{permissionLabel(prefs.browserPermission, t)}</span>
          </p>
          <p className="delivery-status-copy">{summaryLabel}</p>
        </div>

        <div className="delivery-toggle-list">
          <div className={`delivery-toggle ${serverDelivery.morningBriefing ? 'is-active' : ''}`}>
            <span>{t('settings.delivery.morning_briefing')}</span>
            <strong>{enabledLabel(serverDelivery.morningBriefing)}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.weeklyDigest ? 'is-active' : ''}`}>
            <span>{t('settings.delivery.weekly_digest')}</span>
            <strong>{enabledLabel(serverDelivery.weeklyDigest)}</strong>
          </div>
          <div className={`delivery-toggle ${serverDelivery.breakingTopics || serverDelivery.breakingSources ? 'is-active' : ''}`}>
            <span>{t('settings.delivery.breaking_news')}</span>
            <strong>{enabledLabel(serverDelivery.breakingTopics || serverDelivery.breakingSources)}</strong>
          </div>
        </div>

        <div className="delivery-actions">
          <a href={localePathForLang('/settings', lang)} className="delivery-action">
            <Radio size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{t('settings.delivery.open_settings')}</span>
            </span>
          </a>
          <button type="button" className="delivery-action" onClick={copyDigest}>
            <Copy size={14} />
            <span className="delivery-action-content">
              <span className="delivery-action-label">{copyState === 'done' ? t('settings.delivery.copy_done') : copyState === 'error' ? t('settings.delivery.copy_error') : t('settings.delivery.copy_text')}</span>
            </span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="delivery-panel space-y-8">
      <MorningEmailSignup lang={lang as 'sr' | 'mk'} variant="settings" />

      <div className="delivery-status">
        <p className="delivery-status-kicker">
          {prefs.browserPermission === 'granted' ? <BellRing size={14} /> : <Bell size={14} />}
          <span>{permissionLabel(prefs.browserPermission, t)}</span>
        </p>
        <p className="delivery-status-copy">
          {t('settings.delivery.intro')}
        </p>
      </div>

      <div className="delivery-toggle-list space-y-3">
        <button type="button" className={`custom-toggle-btn w-full ${prefs.morningBriefing ? 'is-active' : ''}`} onClick={() => togglePref('morningBriefing')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">{t('settings.delivery.morning_briefing')}</span>
            <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.morning_local_note')}</span>
          </span>
          <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${prefs.morningBriefing ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(prefs.morningBriefing)}</strong>
        </button>
        <button type="button" className={`custom-toggle-btn w-full ${prefs.breakingAlerts ? 'is-active' : ''}`} onClick={() => togglePref('breakingAlerts')}>
          <span className="text-left">
            <span className="block font-sans font-bold text-sm">{t('settings.delivery.breaking_alerts')}</span>
            <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.breaking_alerts_note')}</span>
          </span>
          <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${prefs.breakingAlerts ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(prefs.morningBriefing)}</strong>
        </button>
      </div>

      <div className="delivery-actions">
        <button type="button" className="delivery-action" onClick={requestNotifications}>
          <Bell size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{t('settings.delivery.enable_browser')}</span>
            <span className="delivery-action-note">{t('settings.delivery.enable_browser_note')}</span>
          </span>
        </button>
        <button type="button" className="delivery-action" onClick={copyDigest}>
          <Copy size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{copyState === 'done' ? (t('settings.delivery.copy_done')) : copyState === 'error' ? (t('settings.delivery.copy_error')) : (t('settings.delivery.copy_delivery'))}</span>
            <span className="delivery-action-note">{t('settings.delivery.copy_delivery_note')}</span>
          </span>
        </button>
        <a href={mailHref} className="delivery-action">
          <Mail size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{t('settings.delivery.share_email')}</span>
            <span className="delivery-action-note">{t('settings.delivery.share_email_note')}</span>
          </span>
        </a>
      </div>

      <div className="delivery-digest">
        <p className="delivery-digest-kicker">{t('settings.delivery.preview_kicker')}</p>
        <pre className="digest-paper-view">{digest || (t('settings.delivery.preview_empty'))}</pre>
      </div>

      <div className="scheduled-delivery-panel pt-6 border-t border-border/40">
        <p className="scheduled-delivery-kicker">
          <Radio size={14} />
          <span>{t('settings.delivery.scheduled_kicker')}</span>
        </p>
        <p className="scheduled-delivery-copy">
          {t('settings.delivery.scheduled_copy')}
        </p>

        <label className="scheduled-delivery-label">
          <span>{t('settings.delivery.ntfy_label')}</span>
          <input
            type="text"
            className="account-sync-input"
            value={serverDelivery.target}
            onChange={(e) => updateServerDelivery({ target: e.target.value })}
            placeholder={t('settings.delivery.ntfy_placeholder')}
          />
        </label>

        <div className="delivery-toggle-list space-y-3 mt-4">
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.morningBriefing ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ morningBriefing: !serverDelivery.morningBriefing })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{t('settings.delivery.morning_ntfy')}</span>
              <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.morning_ntfy_note')}</span>
            </span>
            <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.morningBriefing ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(serverDelivery.morningBriefing)}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.weeklyDigest ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ weeklyDigest: !serverDelivery.weeklyDigest })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{t('settings.delivery.weekly_ntfy')}</span>
              <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.weekly_ntfy_note')}</span>
            </span>
            <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.weeklyDigest ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(serverDelivery.weeklyDigest)}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.breakingTopics ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingTopics: !serverDelivery.breakingTopics })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{t('settings.delivery.topic_alerts')}</span>
              <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.topic_alerts_note')}</span>
            </span>
            <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.breakingTopics ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(serverDelivery.weeklyDigest)}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.breakingSources ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ breakingSources: !serverDelivery.breakingSources })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{t('settings.delivery.source_alerts')}</span>
              <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.source_alerts_note')}</span>
            </span>
            <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.breakingSources ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(serverDelivery.weeklyDigest)}</strong>
          </button>
          <button type="button" className={`custom-toggle-btn w-full ${serverDelivery.isActive ? 'is-active' : ''}`} onClick={() => updateServerDelivery({ isActive: !serverDelivery.isActive })}>
            <span className="text-left">
              <span className="block font-sans font-bold text-sm">{t('settings.delivery.scheduled_active')}</span>
              <span className="block text-[11px] md:text-[11px] text-muted-foreground mt-0.5">{t('settings.delivery.scheduled_active_note')}</span>
            </span>
            <strong className={`text-[11px] md:text-[11px] font-black uppercase tracking-[0.14em] md:tracking-widest ${serverDelivery.isActive ? 'text-foreground' : 'text-muted-foreground'}`}>{enabledLabel(serverDelivery.weeklyDigest)}</strong>
          </button>
        </div>

        <button type="button" className="delivery-action mt-6" onClick={saveScheduledDelivery}>
          <Save size={14} />
          <span className="delivery-action-content">
            <span className="delivery-action-label">{t('settings.delivery.save_scheduled')}</span>
            <span className="delivery-action-note">{t('settings.delivery.save_scheduled_note')}</span>
          </span>
        </button>

        {serverMessage && <p className={`account-sync-message is-${serverStatus}`}>{serverMessage}</p>}
      </div>
    </div>
  );
}