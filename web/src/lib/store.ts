import { atom, onMount } from 'nanostores';
import { loadReaderProfile, saveReaderProfile, subscribeToReaderProfile, loadSyncToken } from './personalization.js';
import { apiBaseUrl } from './apiBase.ts';

export const $profile = atom(loadReaderProfile());

onMount($profile, () => {
  const unsubscribe = subscribeToReaderProfile((nextProfile: any) => {
    const current = $profile.get();
    if (JSON.stringify(current) !== JSON.stringify(nextProfile)) {
        $profile.set(nextProfile);
    }
  });
  return () => unsubscribe();
});

export function updateProfile(newProfile: any) {
  const current = $profile.get();
  const merged = { ...current, ...newProfile };
  saveReaderProfile(merged);
}

// Server Sync Logic
let syncTimeout: any = null;
$profile.subscribe((profile) => {
    if (typeof window === 'undefined') return;
    
    if (syncTimeout) clearTimeout(syncTimeout);
    syncTimeout = setTimeout(async () => {
        const token = loadSyncToken();
        if (!token) return;

        try {
            await fetch(`${apiBaseUrl()}/profile/sync`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Sync-Token': token
                },
                body: JSON.stringify({ profile }),
            });
        } catch (e) {
            console.warn("[store] Profile sync failed", e);
        }
    }, 2000);
});

export const $error = atom<string | null>(null);
