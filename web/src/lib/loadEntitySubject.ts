import { apiBaseUrl } from './apiBase';
import { getLangFromUrl, useTranslations } from '../i18n/utils';
import type { ui } from '../i18n/ui';

export async function loadEntitySubject(
  params: { name?: string },
  url: URL,
  hostHeader?: string | null,
) {
  const lang = getLangFromUrl(url, hostHeader);
  const t = useTranslations(lang);
  const decodedName = decodeURIComponent(params.name || '');
  const API_URL = apiBaseUrl();

  let entityData: Record<string, unknown> | null = null;
  let error: string | null = null;
  let httpStatus: number | undefined;

  try {
    const entityRes = await fetch(
      `${API_URL}/intelligence/entity/${encodeURIComponent(decodedName)}?lang=${lang}`,
    );
    if (entityRes.ok) {
      entityData = await entityRes.json();
    } else {
      error = t('entity.error.not_found');
      httpStatus = entityRes.status === 404 ? 404 : 500;
    }
  } catch (e) {
    console.error(e);
    error = t('entity.error.connection');
    httpStatus = 500;
  }

  return {
    lang: lang as keyof typeof ui,
    decodedName,
    entityData,
    error,
    httpStatus,
    hostHeader,
  };
}
