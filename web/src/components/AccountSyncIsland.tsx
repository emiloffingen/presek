import React, { useMemo, useState } from 'react';
import { Copy, Download, KeyRound, RefreshCw, Upload, ShieldCheck, Info } from 'lucide-react';
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
    <div className="account-sync-island">
      <div className="bg-zinc-900 dark:bg-black text-white p-6 rounded-xl shadow-xl border-l-4 border-nyt-accent relative overflow-hidden group">
        <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:rotate-12 transition-transform">
            <ShieldCheck size={80} />
        </div>
        
        <div className="relative z-10">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent mb-2">Статус: {hasToken ? 'АКТИВЕН ПАСОШ' : 'НЕГЕНЕРИРАН'}</p>
            <h4 className="font-serif font-black text-xl mb-4 italic">Дигитален Идентитет</h4>
            
            {hasToken ? (
                <div className="space-y-4">
                    <div className="bg-white/10 p-3 rounded border border-white/10 flex items-center justify-between gap-4">
                        <code className="text-xs font-mono truncate opacity-80">{token}</code>
                        <button onClick={copyToken} className="flex-shrink-0 p-2 hover:text-nyt-accent transition-colors" title="Копирај Клуч">
                            <Copy size={16} />
                        </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <button onClick={() => pushLocalProfile()} className="py-2 bg-white text-black text-[9px] font-black uppercase tracking-widest flex items-center justify-center gap-2 hover:bg-nyt-accent hover:text-white transition-all">
                            <Upload size={12} /> СИНХРОНИЗИРАЈ
                        </button>
                        <button onClick={() => pullRemoteProfile()} className="py-2 bg-transparent border border-white/20 text-white text-[9px] font-black uppercase tracking-widest flex items-center justify-center gap-2 hover:border-nyt-accent hover:text-nyt-accent transition-all">
                            <Download size={12} /> ПРЕЗЕМИ
                        </button>
                    </div>
                </div>
            ) : (
                <button onClick={createSyncKey} className="w-full py-4 bg-nyt-accent text-white text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2 hover:brightness-110 transition-all">
                    <KeyRound size={14} /> КРЕИРАЈ ПАСОШ
                </button>
            )}
        </div>
      </div>

      <div className="mt-8 space-y-4">
        <p className="text-[11px] text-muted-foreground leading-relaxed">
            Користете го овој клуч за да ги носите вашите следења и интереси на друг уред без регистрација.
        </p>
        
        <div className="pt-6 border-t border-border">
            <label className="block text-[9px] font-black uppercase text-muted-foreground mb-2 tracking-widest">Увоз на постоечки клуч</label>
            <div className="flex gap-2">
                <input
                    type="text"
                    value={inputToken}
                    onChange={(e) => setInputToken(e.target.value)}
                    placeholder="Вметнете клуч..."
                    className="flex-grow bg-secondary/30 border border-border rounded px-3 py-2 text-xs font-mono outline-none focus:border-nyt-accent transition-all"
                />
                <button onClick={() => pullRemoteProfile(inputToken)} className="p-2 bg-foreground text-background rounded hover:bg-nyt-accent transition-all">
                    <RefreshCw size={16} className={status === 'working' ? 'animate-spin' : ''} />
                </button>
            </div>
        </div>
      </div>

      {message && (
        <div className={`mt-6 p-4 text-[10px] font-bold rounded flex items-center gap-2 animate-in fade-in ${status === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
            <Info size={12} />
            {message}
        </div>
      )}
    </div>
  );
}
