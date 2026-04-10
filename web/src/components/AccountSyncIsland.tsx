import React, { useMemo, useState } from 'react';
import { Copy, Download, KeyRound, RefreshCw, Upload } from 'lucide-react';
import {
  buildSyncTokenHeaders,
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
      setMessage('Клучот за синхронизација е креиран. Вашиот локален профил е подготвен за синхронизација меѓу уреди.');
    } catch {
      setStatus('error');
      setMessage('Не можев да креирам клуч за синхронизација во моментов.');
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
      setMessage('Локалниот профил е синхронизиран со вашиот клуч за профил.');
    } catch {
      setStatus('error');
      setMessage('Не можев да го испратам овој профил во моментов.');
    }
  };

  const pullRemoteProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || inputToken || token).trim();
    if (!nextToken) return;
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync', {
        headers: buildSyncTokenHeaders(nextToken) as Record<string, string>,
      });
      if (!res.ok) throw new Error('pull failed');
      const data = await res.json();
      mergeSyncPayload(data.profile);
      saveSyncToken(nextToken);
      setToken(nextToken);
      setInputToken(nextToken);
      onTokenChange?.(nextToken);
      setStatus('done');
      setMessage('Синхронизираниот профил е вчитан на овој уред.');
    } catch {
      setStatus('error');
      setMessage('Не можев да го вчитам тој клуч за синхронизација.');
    }
  };

  const copyToken = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setStatus('done');
      setMessage('Клучот за синхронизација е копиран.');
    } catch {
      setStatus('error');
      setMessage('Не можев да го копирам клучот за синхронизација.');
    }
  };

  return (
    <div className="account-sync-panel">
      <p className="account-sync-kicker">
        <KeyRound size={14} />
        <span>Синхронизација на профил</span>
      </p>
      <p className="account-sync-copy">
        Користете еден клуч за синхронизација за да ги носите следените теми, следените извори, поставките за достава и неодамнешното читање меѓу уреди.
      </p>

      <div className="account-sync-controls">
        <button type="button" className="delivery-action" onClick={createSyncKey}>
          <KeyRound size={14} /> {hasToken ? 'Креирај нов клуч за синхронизација' : 'Креирај клуч за синхронизација'}
        </button>
        {hasToken && (
          <>
            <button type="button" className="delivery-action" onClick={() => pushLocalProfile()}>
              <Upload size={14} /> Синхронизирај го овој уред
            </button>
            <button type="button" className="delivery-action" onClick={() => pullRemoteProfile()}>
              <Download size={14} /> Вчитај синхронизиран профил
            </button>
            <button type="button" className="delivery-action" onClick={copyToken}>
              <Copy size={14} /> Копирај клуч за синхронизација
            </button>
          </>
        )}
      </div>

      <label className="account-sync-label">
        <span>Користи постоечки клуч за синхронизација</span>
        <div className="account-sync-import">
          <input
            type="text"
            value={inputToken}
            onChange={(e) => setInputToken(e.target.value)}
            placeholder="Вметнете го вашиот клуч за синхронизација"
            className="account-sync-input"
          />
          <button type="button" className="delivery-action account-sync-import-btn" onClick={() => pullRemoteProfile(inputToken)}>
            <RefreshCw size={14} /> Поврзи
          </button>
        </div>
      </label>

      {token && <p className="account-sync-token">Тековен клуч: {token}</p>}
      {message && <p className={`account-sync-message is-${status}`}>{message}</p>}
    </div>
  );
}
