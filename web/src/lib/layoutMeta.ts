import { buildCanonicalUrl, siteOrigin, type Locale } from './localePaths.ts';

export function siteDisplayName(lang: Locale): string {
  return lang === 'sr' ? 'PRESEK.rs' : 'PRESEK.mk';
}

export function buildPageTitle(title: string, lang: Locale): string {
  const siteName = siteDisplayName(lang);
  if (title.includes('Presek') || title.includes('Пресек')) {
    return title.replace(/Presek|Пресек/, siteName);
  }
  return `${title} | ${siteName}`;
}

/**
 * Social profile URLs for a locale. Profiles are keyed off the site's own TLD so
 * a .mk deployment never advertises .rs (Serbian) accounts, and vice versa.
 */
export function socialProfiles(lang: Locale): string[] {
  return lang === 'sr'
    ? [
        'https://twitter.com/presek_rs',
        'https://facebook.com/presek.rs',
        'https://instagram.com/presek.rs',
      ]
    : [
        'https://twitter.com/presek_mk',
        'https://facebook.com/presek.mk',
        'https://instagram.com/presek.mk',
      ];
}

export function buildOrganizationSchema(lang: Locale) {
  const siteUrl = siteOrigin(lang);
  const siteName = siteDisplayName(lang);
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': `${siteUrl}/#organization`,
    name: siteName,
    url: siteUrl,
    logo: {
      '@type': 'ImageObject',
      url: `${siteUrl}/img/presek_emblem.png`,
      width: 512,
      height: 512,
    },
    sameAs: socialProfiles(lang),
  };
}

export function resolveLayoutUrls(
  pathname: string,
  lang: Locale,
  image: string,
  canonical?: string,
) {
  const siteUrl = siteOrigin(lang);
  const canonicalUrl = canonical || buildCanonicalUrl(pathname, lang);
  const imageUrl = /^https?:\/\//i.test(image)
    ? image
    : `${siteUrl}${image.startsWith('/') ? image : `/${image}`}`;
  return { siteUrl, canonicalUrl, imageUrl };
}

export function gtagIdForLang(lang: Locale): string {
  return lang === 'mk' ? 'G-YJZH9KK8X9' : 'G-SV2R3LZJ5C';
}
