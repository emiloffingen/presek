export const languages = {
  sr: 'Srpski',
  mk: 'Makedonski',
} as const;

export const defaultLang = 'sr';

export type Locale = keyof typeof languages;

export const localeCodes = Object.keys(languages) as Locale[];

export function isLocale(value: string): value is Locale {
  return value in languages;
}
