import React, { useMemo, useState } from 'react';
import { Copy, Download, KeyRound, RefreshCw, Upload } from 'lucide-react';
import {
  exportSyncPayload,
  loadSyncToken,
  mergeSyncPayload,
  saveSyncToken,
} from '../lib/personalization.js';

type SyncState = 'idle' | 'working' | 'done' | 'error';

export default function AccountSyncIsland({
  onTokenChange,
}: {
  onTokenChange?: (token: string) => void;
}) {
  const [token, setToken] = useState(() => loadSyncToken());
  const [inputToken, setInputToken] = useState('');
  const [status, setStatus] = useState<SyncState>('idle');
  const [message, setMessage] = useState('');

  const hasToken = useMemo(() => token.trim().length > 0, [token]);

  const createSyncKey = async () => {
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync/init', { method: 'POST' });
      if (!res.ok) throw new Error('init failed');
      const data = await res.json();
      const nextToken = saveSyncToken(data.token);
      setToken(nextToken);
      setInputToken(nextToken);
      onTokenChange?.(nextToken);
      setStatus('done');
      setMessage('Sync key created. Your local profile is ready to sync across devices.');
    } catch {
      setStatus('error');
      setMessage('Could not create a sync key right now.');
    }
  };

  const pushLocalProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || token).trim();
    if (!nextToken) return;
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: nextToken,
          profile: exportSyncPayload(),
        }),
      });
      if (!res.ok) throw new Error('push failed');
      const data = await res.json();
      mergeSyncPayload(data.profile);
      saveSyncToken(nextToken);
      setToken(nextToken);
      onTokenChange?.(nextToken);
      setStatus('done');
      setMessage('Local profile synced to your account key.');
    } catch {
      setStatus('error');
      setMessage('Could not push this profile right now.');
    }
  };

  const pullRemoteProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || inputToken || token).trim();
    if (!nextToken) return;
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch(`/api/profile/sync?token=${encodeURIComponent(nextToken)}`);
      if (!res.ok) throw new Error('pull failed');
      const data = await res.json();
      mergeSyncPayload(data.profile);
      saveSyncToken(nextToken);
      setToken(nextToken);
      setInputToken(nextToken);
      onTokenChange?.(nextToken);
      setStatus('done');
      setMessage('Synced profile loaded on this device.');
    } catch {
      setStatus('error');
      setMessage('Could not load that sync key.');
    }
  };

  const copyToken = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setStatus('done');
      setMessage('Sync key copied.');
    } catch {
      setStatus('error');
      setMessage('Could not copy the sync key.');
    }
  };

  return (
    <div className="account-sync-panel">
      <p className="account-sync-kicker">
        <KeyRound size={14} />
        <span>Account sync</span>
      </p>
      <p className="account-sync-copy">
        Use one sync key to carry followed topics, followed sources, delivery preferences, and recent reading across devices.
      </p>

      <div className="account-sync-controls">
        <button type="button" className="delivery-action" onClick={createSyncKey}>
          <KeyRound size={14} /> {hasToken ? 'Create new sync key' : 'Create sync key'}
        </button>
        {hasToken && (
          <>
            <button type="button" className="delivery-action" onClick={() => pushLocalProfile()}>
              <Upload size={14} /> Sync this device
            </button>
            <button type="button" className="delivery-action" onClick={() => pullRemoteProfile()}>
              <Download size={14} /> Load synced profile
            </button>
            <button type="button" className="delivery-action" onClick={copyToken}>
              <Copy size={14} /> Copy sync key
            </button>
          </>
        )}
      </div>

      <label className="account-sync-label">
        <span>Use an existing sync key</span>
        <div className="account-sync-import">
          <input
            type="text"
            value={inputToken}
            onChange={(e) => setInputToken(e.target.value)}
            placeholder="Paste your sync key"
            className="account-sync-input"
          />
          <button type="button" className="delivery-action account-sync-import-btn" onClick={() => pullRemoteProfile(inputToken)}>
            <RefreshCw size={14} /> Connect
          </button>
        </div>
      </label>

      {token && <p className="account-sync-token">Current key: {token}</p>}
      {message && <p className={`account-sync-message is-${status}`}>{message}</p>}
    </div>
  );
}
