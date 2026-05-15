import { ui, defaultLang } from './ui';

export function getLangFromUrl(url: URL) {
  const [, lang] = url.pathname.split('/');
  
  // Check domain first for Macedonian site
  if (url.hostname === 'presek.mk' || url.hostname === 'www.presek.mk') {
    return 'mk' as keyof typeof ui;
  }
  
  // Fall back to path-based detection for Serbian site
  if (lang in ui) return lang as keyof typeof ui;
  return defaultLang;
}

export function useTranslations(lang: keyof typeof ui) {
  return function t(key: keyof typeof ui[typeof defaultLang]) {
    return ui[lang][key] || ui[defaultLang][key];
  }
}
