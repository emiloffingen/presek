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
  const latestRef = useRef(state);
  latestRef.current = state;

  const write = (s: SearchSessionState) => {
    try {
      if (s.isOpen) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
      } else {
        sessionStorage.removeItem(SESSION_KEY);
      }
    } catch (e) {}
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(() => {
      debounceRef.current = null;
      write(latestRef.current);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
    // Depend on primitives so a new `state` object identity each render does not
    // restart the debounce; the latest values are read via latestRef.
  }, [state.query, state.timespan, state.categoryFilter, state.isOpen]);

  // Flush on unmount: a pending close/remove must persist, otherwise a stale
  // "open" session is restored on the next mount.
  useEffect(() => () => {
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    write(latestRef.current);
  }, []);
}

export function loadSearchSession(): Partial<SearchSessionState> | null {
  if (typeof window === 'undefined') return null;
  let raw = null;
  try {
    raw = sessionStorage.getItem(SESSION_KEY);
  } catch (e) {}
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const v = parsed as Record<string, unknown>;
    if (
      (v.query !== undefined && typeof v.query !== 'string') ||
      (v.timespan !== undefined && typeof v.timespan !== 'string') ||
      (v.categoryFilter !== undefined && typeof v.categoryFilter !== 'string') ||
      (v.isOpen !== undefined && typeof v.isOpen !== 'boolean')
    ) {
      return null;
    }
    return v as Partial<SearchSessionState>;
  } catch {
    return null;
  }
}
