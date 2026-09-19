import { ui, defaultLang } from './ui';
import { isLocale, type Locale } from './config';

export function getLangFromUrl(url: URL, hostname?: string | null): Locale {
  const [, lang] = url.pathname.split('/');

  const effectiveHost = hostname || url.hostname;

  // Check domain first for Macedonian site
  if (effectiveHost === 'presek.mk' || effectiveHost === 'www.presek.mk') {
    return 'mk';
  }

  // Macedonian is the sole public edition. Keep explicit legacy locale paths
  // detectable for redirects and compatibility, but default everything else to MK.
  if (isLocale(lang)) return lang;
  return 'mk';
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
