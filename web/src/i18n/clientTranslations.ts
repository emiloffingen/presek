import type { Locale } from './config';

type NamespaceBundle = Record<Locale, Record<string, string>>;

function mergeNamespaces(lang: Locale, parts: readonly NamespaceBundle[]): Record<string, string> {
  const merged: Record<string, string> = {};
  for (const part of parts) {
    Object.assign(merged, part.sr);
  }
  for (const part of parts) {
    Object.assign(merged, part[lang]);
  }
  return merged;
}

/** Client islands only — pass the namespace modules this island actually uses. */
export function useClientTranslations(
  lang: Locale,
  ...parts: NamespaceBundle[]
) {
  const dict = mergeNamespaces(lang, parts);
  return function t(key: string, params?: Record<string, string | number>): string {
    let value = dict[key] ?? key;
    if (params) {
      for (const [paramKey, paramValue] of Object.entries(params)) {
        value = value.replaceAll(`{${paramKey}}`, String(paramValue));
      }
    }
    return value;
  };
}
