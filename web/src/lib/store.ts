import { atom, onMount } from 'nanostores';
import { 
    loadReaderProfile, 
    saveReaderProfile, 
    subscribeToReaderProfile, 
    loadSyncToken, 
    saveSyncToken,
    subscribeToSyncToken,
    loadDeliveryPreferences,
    saveDeliveryPreferences,
    subscribeToDeliveryPrefs,
    loadOnboardingState,
    saveOnboardingState,
    subscribeToOnboarding,
    getOnboardingProgress
} from './personalization.js';
import { apiBaseUrl } from './apiBase.ts';

// Atoms
export const $profile = atom(loadReaderProfile());
export const $syncToken = atom(loadSyncToken());
export const $deliveryPrefs = atom(loadDeliveryPreferences());
export const $onboarding = atom(loadOnboardingState());

// Mounts for cross-tab synchronization and library bridge
onMount($profile, () => {
  const unsubscribe = subscribeToReaderProfile((nextProfile: any) => {
    const current = $profile.get();
    if (JSON.stringify(current) !== JSON.stringify(nextProfile)) {
        $profile.set(nextProfile);
    }
  });
  return () => unsubscribe();
});

onMount($syncToken, () => {
    const unsubscribe = subscribeToSyncToken((nextToken: string) => {
        if ($syncToken.get() !== nextToken) {
            $syncToken.set(nextToken);
        }
    });
    return () => unsubscribe();
});

onMount($deliveryPrefs, () => {
    const unsubscribe = subscribeToDeliveryPrefs((nextPrefs: any) => {
        const current = $deliveryPrefs.get();
        if (JSON.stringify(current) !== JSON.stringify(nextPrefs)) {
            $deliveryPrefs.set(nextPrefs);
        }
    });
    return () => unsubscribe();
});

onMount($onboarding, () => {
    const unsubscribe = subscribeToOnboarding((nextState: any) => {
        const current = $onboarding.get();
        if (JSON.stringify(current) !== JSON.stringify(nextState)) {
            $onboarding.set(nextState);
        }
    });
    return () => unsubscribe();
});

// Helper: Batch update for profile
export function updateProfile(newProfile: any) {
  const current = $profile.get();
  const merged = { ...current, ...newProfile };
  const saved = saveReaderProfile(merged);
  $profile.set(saved);
}

// Helper: Update sync token
export function updateSyncToken(token: string) {
    const saved = saveSyncToken(token);
    $syncToken.set(saved);
}

// Helper: Update delivery preferences
export function updateDeliveryPrefs(newPrefs: any) {
    const current = $deliveryPrefs.get();
    const merged = { ...current, ...newPrefs };
    const saved = saveDeliveryPreferences(merged);
    $deliveryPrefs.set(saved);
}

// Helper: Update onboarding state
export function updateOnboarding(newState: any) {
    const current = $onboarding.get();
    const merged = { ...current, ...newState };
    const saved = saveOnboardingState(merged);
    $onboarding.set(saved);
}

// Computed progress (not an atom to keep it simple, but can be derived in components)
export function getStoredOnboardingProgress() {
    return getOnboardingProgress();
}

// Server Sync Logic for Profile
let syncTimeout: any = null;
$profile.subscribe((profile) => {
    if (typeof window === 'undefined') return;
    
    if (syncTimeout) {
      if (typeof clearTimeout === 'function') clearTimeout(syncTimeout);
    }
    syncTimeout = setTimeout(async () => {
        const token = $syncToken.get();
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
