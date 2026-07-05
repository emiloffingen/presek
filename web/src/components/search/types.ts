import type { LucideIcon } from 'lucide-react';
import type { Locale } from '../../lib/localePaths';

export type TFunction = (key: string, params?: Record<string, string | number>) => string;

export type Suggestion = {
  cluster_id: string;
  title: string;
  image_url?: string | null;
  source?: string;
  category?: string;
  description?: string;
  sourceCount?: number;
  matchLabel?: string;
  created_at?: string;
  representative_image?: string;
  pulse_score?: number;
  has_synthesis?: boolean;
};

export type EntityResult = {
  name: string;
  type: string;
  total_mentions: number;
  sentiment_score: number;
  image_url?: string | null;
};

export type TrendingItem = {
  word: string;
};

export type SearchActionCategory = 'NAVIGATION' | 'SETTINGS' | 'HELP';

export type SearchAction = {
  id: string;
  label: string;
  icon: LucideIcon;
  href: string;
  category: SearchActionCategory;
  desc: string;
};

export type CategoryOption = {
  id: string;
  labelKey: string;
  /** Value sent to the search API for this category. */
  apiValue: string;
  color: string;
};

export type TimespanOption = {
  id: string;
  labelKey: string;
};

export type RecentSearch = {
  query: string;
  timestamp: number;
};

export type SelectedItem =
  | { type: 'ENTITY'; data: EntityResult }
  | { type: 'CLUSTER'; data: Suggestion }
  | { type: 'ACTION'; data: SearchAction };

export type SearchSessionState = {
  query: string;
  timespan: string;
  categoryFilter: string;
  isOpen: boolean;
};

export type SearchIslandProps = {
  initialQuery?: string | null;
  lang?: Locale;
  startOpen?: boolean;
  hideTrigger?: boolean;
  onClose?: () => void;
};

// Minimal typed wrappers for the Web Speech API so we avoid `any`.
export interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

export interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

export interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  readonly isFinal: boolean;
}

export interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

export interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null;
  onend: ((this: SpeechRecognition, ev: Event) => void) | null;
  onerror: ((this: SpeechRecognition, ev: Event) => void) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export interface SpeechRecognitionConstructor {
  new (): SpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export {};
