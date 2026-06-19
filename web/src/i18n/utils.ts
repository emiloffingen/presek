import { ui, defaultLang } from './ui';
import { isLocale, type Locale } from './config';

export function getLangFromUrl(url: URL, hostname?: string | null): Locale {
  const [, lang] = url.pathname.split('/');

  const effectiveHost = hostname || url.hostname;

  // Check domain first for Macedonian site
  if (effectiveHost === 'presek.mk' || effectiveHost === 'www.presek.mk') {
    return 'mk';
  }

  // Fall back to path-based detection for Serbian site
  if (isLocale(lang)) return lang;
  return defaultLang;
}

export function useTranslations(lang: keyof typeof ui) {
  return function t(
    key: keyof typeof ui[typeof defaultLang],
    params?: Record<string, string | number>
  ) {
    let value: string = ui[lang][key] || ui[defaultLang][key];

    if (params) {
      for (const [paramKey, paramValue] of Object.entries(params)) {
        value = value.replaceAll(`{${paramKey}}`, String(paramValue));
      }
    }

    return value;
  }
}
