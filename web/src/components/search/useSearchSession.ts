import { useEffect, useRef } from 'react';
import type { SearchSessionState } from './types';

const SESSION_KEY = 'presek_search_session_state';
const DEBOUNCE_MS = 250;

/**
 * Persist lightweight search session state to sessionStorage with a small
 * debounce so keystrokes don't block the main thread.
 */
export function useSearchSession(state: SearchSessionState) {
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(() => {
      debounceRef.current = null;
      if (state.isOpen) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
      } else {
        sessionStorage.removeItem(SESSION_KEY);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [state]);
}

export function loadSearchSession(): Partial<SearchSessionState> | null {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Partial<SearchSessionState>;
  } catch {
    return null;
  }
}
